"""
TEST-02: Unit tests for all 7 LangGraph node functions.

LLM calls are mocked — no real API keys or network required.
"""
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_state(**overrides):
    """Return a minimal valid AgentState dict."""
    state = {
        "resume_text": "Jane Doe\njane@example.com\nSkills: Python, FastAPI\nExperience: 3 years",
        "job_description": "We need a Python engineer with FastAPI and Kubernetes experience.",
        "user_id": 1,
        "session_id": "test-session-123",
        "resume_parsed": None,
        "jd_parsed": None,
        "gap_analysis": None,
        "tailored_bullets": None,
        "cover_letter": None,
        "interview_qa": None,
        "ats_score": None,
        "next_agent": "",
        "completed_agents": [],
        "messages": [],
        "error": None,
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# supervisor_node — pure logic, no mocking needed
# ---------------------------------------------------------------------------

class TestSupervisorNode:
    def test_routes_to_first_agent_when_nothing_completed(self):
        from agents.nodes.supervisor import supervisor_node
        result = supervisor_node(_base_state())
        assert result["next_agent"] == "resume_parser"

    def test_routes_to_next_pending_agent(self):
        from agents.nodes.supervisor import supervisor_node
        state = _base_state(completed_agents=["resume_parser", "jd_analyst"])
        result = supervisor_node(state)
        assert result["next_agent"] == "company_researcher"

    def test_routes_to_end_when_all_completed(self):
        from agents.nodes.supervisor import supervisor_node
        all_agents = [
            "resume_parser", "jd_analyst", "company_researcher", "gap_analyst",
            "resume_tailor", "cover_letter", "interview_coach", "ats_scorer",
        ]
        result = supervisor_node(_base_state(completed_agents=all_agents))
        assert result["next_agent"] == "END"

    def test_preserves_existing_state_fields(self):
        from agents.nodes.supervisor import supervisor_node
        state = _base_state(resume_text="original text")
        result = supervisor_node(state)
        assert result["resume_text"] == "original text"


# ---------------------------------------------------------------------------
# resume_parser_node
# ---------------------------------------------------------------------------

class TestResumeParserNode:
    def _mock_parsed_resume(self):
        return MagicMock(model_dump=lambda: {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "555-1234",
            "skills": ["Python", "FastAPI"],
            "experience": [{"company": "Acme", "role": "Engineer", "duration": "2y", "bullets": ["Built APIs"]}],
            "education": [{"institution": "MIT", "degree": "BS CS", "year": 2020}],
            "summary": "Software engineer",
        })

    @patch("agents.nodes.resume_parser.index_documents")
    @patch("agents.nodes.resume_parser.invoke_structured")
    def test_happy_path(self, mock_invoke_structured, mock_index):
        from agents.nodes.resume_parser import resume_parser_node
        mock_invoke_structured.return_value = self._mock_parsed_resume()

        result = resume_parser_node(_base_state())

        assert result["resume_parsed"]["name"] == "Jane Doe"
        assert "resume_parser" in result["completed_agents"]
        assert result["error"] is None

    @patch("agents.nodes.resume_parser.index_documents")
    @patch("agents.nodes.resume_parser.invoke_structured")
    def test_rag_failure_does_not_abort(self, mock_invoke_structured, mock_index):
        from agents.nodes.resume_parser import resume_parser_node
        mock_index.side_effect = Exception("ChromaDB unavailable")
        mock_invoke_structured.return_value = self._mock_parsed_resume()

        result = resume_parser_node(_base_state())

        # Should still succeed — RAG errors are swallowed
        assert result["resume_parsed"] is not None
        assert result["error"] is None

    @patch("agents.nodes.resume_parser.index_documents")
    @patch("agents.nodes.resume_parser.ChatGroq")
    def test_llm_failure_sets_error(self, mock_llm_cls, mock_index):
        from agents.nodes.resume_parser import resume_parser_node
        mock_llm_cls.side_effect = Exception("API error")

        result = resume_parser_node(_base_state())

        assert result["error"] is not None
        assert "resume_parser" in result["completed_agents"]


# ---------------------------------------------------------------------------
# jd_analyst_node
# ---------------------------------------------------------------------------

class TestJDAnalystNode:
    def _mock_parsed_jd(self):
        return MagicMock(model_dump=lambda: {
            "job_title": "Python Engineer",
            "company": "TechCorp",
            "required_skills": ["Python", "FastAPI", "Kubernetes"],
            "nice_to_have_skills": ["Docker"],
            "experience_years": 3,
            "responsibilities": ["Build APIs"],
            "keywords": ["Python", "REST", "microservices"],
        })

    @patch("agents.nodes.jd_analyst.index_documents")
    @patch("agents.nodes.jd_analyst.invoke_structured")
    def test_happy_path(self, mock_invoke_structured, mock_index):
        from agents.nodes.jd_analyst import jd_analyst_node
        mock_invoke_structured.return_value = self._mock_parsed_jd()

        result = jd_analyst_node(_base_state())

        assert result["jd_parsed"]["job_title"] == "Python Engineer"
        assert "jd_analyst" in result["completed_agents"]
        assert result["error"] is None

    @patch("agents.nodes.jd_analyst.index_documents")
    @patch("agents.nodes.jd_analyst.ChatGroq")
    def test_llm_failure_sets_error(self, mock_llm_cls, mock_index):
        from agents.nodes.jd_analyst import jd_analyst_node
        mock_llm_cls.side_effect = Exception("timeout")

        result = jd_analyst_node(_base_state())

        assert result["error"] is not None
        assert "jd_analyst" in result["completed_agents"]


# ---------------------------------------------------------------------------
# gap_analyst_node
# ---------------------------------------------------------------------------

class TestGapAnalystNode:
    def _mock_gap_analysis(self):
        return MagicMock(model_dump=lambda: {
            "matching_skills": ["Python", "FastAPI"],
            "missing_skills": ["Kubernetes"],
            "partial_matches": [],
            "match_percentage": 66.7,
            "summary": "Good match, missing Kubernetes.",
        })

    def _state_with_parsed(self):
        return _base_state(
            resume_parsed={"skills": ["Python", "FastAPI"], "experience": []},
            jd_parsed={"job_title": "Python Engineer", "required_skills": ["Python", "FastAPI", "Kubernetes"]},
        )

    @patch("agents.nodes.gap_analyst.query_collection", return_value=[])
    @patch("agents.nodes.gap_analyst.ChatGroq")
    def test_happy_path(self, mock_llm_cls, mock_query):
        from agents.nodes.gap_analyst import gap_analyst_node
        structured_llm = MagicMock()
        structured_llm.invoke.return_value = self._mock_gap_analysis()
        mock_llm_cls.return_value.with_structured_output.return_value = structured_llm

        result = gap_analyst_node(self._state_with_parsed())

        assert result["gap_analysis"]["match_percentage"] == 66.7
        assert "gap_analyst" in result["completed_agents"]
        assert result["error"] is None

    @patch("agents.nodes.gap_analyst.query_collection", side_effect=Exception("chroma down"))
    @patch("agents.nodes.gap_analyst.ChatGroq")
    def test_rag_failure_does_not_abort(self, mock_llm_cls, mock_query):
        from agents.nodes.gap_analyst import gap_analyst_node
        structured_llm = MagicMock()
        structured_llm.invoke.return_value = self._mock_gap_analysis()
        mock_llm_cls.return_value.with_structured_output.return_value = structured_llm

        result = gap_analyst_node(self._state_with_parsed())

        assert result["gap_analysis"] is not None
        assert result["error"] is None

    @patch("agents.nodes.gap_analyst.query_collection", return_value=[])
    @patch("agents.nodes.gap_analyst.ChatGroq")
    def test_llm_failure_sets_error(self, mock_llm_cls, mock_query):
        from agents.nodes.gap_analyst import gap_analyst_node
        # Make ChatGroq() instantiation fail — this is inside the outer try so it sets error
        mock_llm_cls.side_effect = Exception("rate limit")

        result = gap_analyst_node(self._state_with_parsed())

        assert result["error"] is not None
        assert "gap_analyst" in result["completed_agents"]


# ---------------------------------------------------------------------------
# resume_tailor_node
# ---------------------------------------------------------------------------

class TestResumeTailorNode:
    def _mock_tailored(self):
        bullet = MagicMock(model_dump=lambda: {
            "original": "Built APIs",
            "tailored": "Engineered REST APIs with FastAPI",
            "reasoning": "Incorporated FastAPI keyword",
        })
        return MagicMock(bullets=[bullet])

    def _state_with_bullets(self):
        return _base_state(
            resume_parsed={"experience": [{"bullets": ["Built APIs", "Led team"]}]},
            jd_parsed={"keywords": ["FastAPI", "REST"]},
            gap_analysis={"missing_skills": ["Kubernetes"]},
        )

    @patch("agents.nodes.resume_tailor.invoke_structured")
    def test_happy_path(self, mock_invoke_structured):
        from agents.nodes.resume_tailor import resume_tailor_node
        mock_invoke_structured.return_value = self._mock_tailored()

        result = resume_tailor_node(self._state_with_bullets())

        assert len(result["tailored_bullets"]) == 1
        assert result["tailored_bullets"][0]["tailored"] == "Engineered REST APIs with FastAPI"
        assert "resume_tailor" in result["completed_agents"]

    @patch("agents.nodes.resume_tailor.ChatGroq")
    def test_empty_bullets_skips_llm(self, mock_llm_cls):
        from agents.nodes.resume_tailor import resume_tailor_node
        state = _base_state(
            resume_parsed={"experience": []},
            jd_parsed={},
            gap_analysis={},
        )
        result = resume_tailor_node(state)

        mock_llm_cls.assert_not_called()
        assert result["tailored_bullets"] == []
        assert "resume_tailor" in result["completed_agents"]

    @patch("agents.nodes.resume_tailor.ChatGroq")
    def test_llm_failure_sets_error(self, mock_llm_cls):
        from agents.nodes.resume_tailor import resume_tailor_node
        mock_llm_cls.side_effect = Exception("error")

        result = resume_tailor_node(self._state_with_bullets())

        assert result["error"] is not None
        assert "resume_tailor" in result["completed_agents"]


# ---------------------------------------------------------------------------
# cover_letter_node
# ---------------------------------------------------------------------------

class TestCoverLetterNode:
    def _state_with_context(self):
        return _base_state(
            resume_parsed={"name": "Jane Doe", "summary": "Engineer", "experience": []},
            jd_parsed={"job_title": "Python Engineer", "company": "TechCorp"},
            gap_analysis={"matching_skills": ["Python"]},
        )

    @patch("agents.nodes.cover_letter.ChatGroq")
    def test_happy_path(self, mock_llm_cls):
        from agents.nodes.cover_letter import cover_letter_node
        mock_response = MagicMock()
        mock_response.content = "  Dear Hiring Manager, I am excited...  "
        mock_llm_cls.return_value.invoke.return_value = mock_response

        result = cover_letter_node(self._state_with_context())

        assert result["cover_letter"] == "Dear Hiring Manager, I am excited..."
        assert "cover_letter" in result["completed_agents"]
        assert result["error"] is None

    @patch("agents.nodes.cover_letter.ChatGroq")
    def test_llm_failure_sets_error(self, mock_llm_cls):
        from agents.nodes.cover_letter import cover_letter_node
        mock_llm_cls.return_value.invoke.side_effect = Exception("network error")

        result = cover_letter_node(self._state_with_context())

        assert result["error"] is not None
        assert "cover_letter" in result["completed_agents"]


# ---------------------------------------------------------------------------
# interview_coach_node
# ---------------------------------------------------------------------------

class TestInterviewCoachNode:
    def _mock_qa_list(self):
        qa = MagicMock(model_dump=lambda: {
            "question": "Tell me about yourself",
            "type": "behavioral",
            "model_answer": "I am a Python engineer with 3 years of experience.",
        })
        return MagicMock(qa_pairs=[qa])

    def _state_with_context(self):
        return _base_state(
            resume_parsed={"name": "Jane Doe", "skills": ["Python"]},
            jd_parsed={"job_title": "Python Engineer"},
            gap_analysis={"missing_skills": ["Kubernetes"]},
        )

    @patch("agents.nodes.interview_coach.invoke_structured")
    def test_happy_path(self, mock_invoke_structured):
        from agents.nodes.interview_coach import interview_coach_node
        mock_invoke_structured.return_value = self._mock_qa_list()

        result = interview_coach_node(self._state_with_context())

        assert len(result["interview_qa"]) == 1
        assert result["interview_qa"][0]["type"] == "behavioral"
        assert "interview_coach" in result["completed_agents"]
        assert result["error"] is None

    @patch("agents.nodes.interview_coach.ChatGroq")
    def test_llm_failure_sets_error(self, mock_llm_cls):
        from agents.nodes.interview_coach import interview_coach_node
        mock_llm_cls.side_effect = Exception("timeout")

        result = interview_coach_node(self._state_with_context())

        assert result["error"] is not None
        assert "interview_coach" in result["completed_agents"]


# ---------------------------------------------------------------------------
# ats_scorer_node
# ---------------------------------------------------------------------------

class TestATSScorerNode:
    def _mock_ats_score(self):
        return MagicMock(model_dump=lambda: {
            "score": 78,
            "keyword_matches": ["Python", "FastAPI"],
            "keyword_misses": ["Kubernetes"],
            "formatting_suggestions": ["Use standard section headers"],
            "overall_assessment": "Good match. Add Kubernetes to improve score.",
        })

    def _state_with_context(self):
        return _base_state(
            resume_parsed={"skills": ["Python", "FastAPI"]},
            jd_parsed={"keywords": ["Python", "FastAPI", "Kubernetes"]},
            tailored_bullets=[{"tailored": "Built REST APIs"}],
            # Score is pinned to gap_analysis.match_percentage — must be set
            gap_analysis={"match_percentage": 78.0},
        )

    @patch("agents.nodes.ats_scorer.invoke_structured")
    def test_happy_path(self, mock_invoke_structured):
        from agents.nodes.ats_scorer import ats_scorer_node
        mock_invoke_structured.return_value = self._mock_ats_score()

        result = ats_scorer_node(self._state_with_context())

        assert result["ats_score"]["score"] == 78
        assert "Kubernetes" in result["ats_score"]["keyword_misses"]
        assert "ats_scorer" in result["completed_agents"]
        assert result["error"] is None

    @patch("agents.nodes.ats_scorer.ChatGroq")
    def test_llm_failure_sets_error(self, mock_llm_cls):
        from agents.nodes.ats_scorer import ats_scorer_node
        mock_llm_cls.side_effect = Exception("API error")

        result = ats_scorer_node(self._state_with_context())

        assert result["error"] is not None
        assert "ats_scorer" in result["completed_agents"]
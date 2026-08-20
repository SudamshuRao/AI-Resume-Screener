from langgraph.graph import StateGraph, END

from agents.state import AgentState
from agents.nodes.supervisor import supervisor_node
from agents.nodes.resume_parser import resume_parser_node
from agents.nodes.jd_analyst import jd_analyst_node
from agents.nodes.company_researcher import company_researcher_node
from agents.nodes.gap_analyst import gap_analyst_node
from agents.nodes.resume_tailor import resume_tailor_node
from agents.nodes.cover_letter import cover_letter_node
from agents.nodes.interview_coach import interview_coach_node
def build_graph():
    """Construct and compile the HireIQ LangGraph StateGraph.

    Pipeline order (enforced by the supervisor):
        supervisor -> resume_parser -> jd_analyst -> company_researcher ->
        gap_analyst -> resume_tailor -> cover_letter -> interview_coach ->
        ats_scorer -> END

    Each agent node routes back to the supervisor, which then decides the
    next step based on state["completed_agents"].

    Returns:
        A compiled LangGraph graph ready for .invoke() / .ainvoke().
    """
    workflow = StateGraph(AgentState)

    # Register all nodes.
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("resume_parser", resume_parser_node)
    workflow.add_node("jd_analyst", jd_analyst_node)
    workflow.add_node("company_researcher", company_researcher_node)
    workflow.add_node("gap_analyst", gap_analyst_node)
    workflow.add_node("resume_tailor", resume_tailor_node)
    workflow.add_node("cover_letter_writer", cover_letter_node)
    workflow.add_node("interview_coach", interview_coach_node)

    # The supervisor is always the entry point.
    workflow.set_entry_point("supervisor")

    # Supervisor uses conditional edges to route to the appropriate agent.
    workflow.add_conditional_edges(
        "supervisor",
        lambda state: state["next_agent"],
        {
            "resume_parser": "resume_parser",
            "jd_analyst": "jd_analyst",
            "company_researcher": "company_researcher",
            "gap_analyst": "gap_analyst",
            "resume_tailor": "resume_tailor",
            "cover_letter": "cover_letter_writer",
            "interview_coach": "interview_coach",
            "END": END,
        },
    )

    # Each agent node routes back to the supervisor after completion.
    agent_nodes = [
        "resume_parser",
        "jd_analyst",
        "company_researcher",
        "gap_analyst",
        "resume_tailor",
        "cover_letter_writer",
        "interview_coach",
    ]
    for node in agent_nodes:
        workflow.add_edge(node, "supervisor")

    return workflow.compile()
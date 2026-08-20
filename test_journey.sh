#!/bin/bash
set -e

TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyIiwiZW1haWwiOiJ0ZXN0dXNlckBoaXJlaXEuZGV2IiwiZXhwIjoxNzc0NDI4OTg3fQ.8JohNULtS36nxRtMUBc_eiaTPZoMkkdJq7eD23psg9A"

echo "=== STEP 4: Create Application ==="
curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST http://localhost:8000/api/v1/applications \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d @- <<'PAYLOAD'
{
  "company": "Anthropic",
  "job_title": "Senior Machine Learning Engineer",
  "job_description": "We are looking for a Senior ML Engineer to join our team. Requirements: 5+ years of Python, deep experience with PyTorch or TensorFlow, experience with LLMs, transformers, and RLHF. Nice to have: experience with distributed training, MLOps, and cloud platforms (AWS/GCP). Responsibilities: design and implement ML models, lead research projects, collaborate with cross-functional teams.",
  "resume_text": "John Smith\njohn.smith@email.com | (555) 123-4567\n\nSKILLS\nPython, PyTorch, TensorFlow, scikit-learn, SQL, AWS, Docker, Kubernetes, LLMs, Transformers\n\nEXPERIENCE\nML Engineer TechCorp (2020-2024)\n- Built and deployed 3 production ML models serving 1M+ requests/day\n- Implemented RLHF pipeline reducing hallucinations by 40%\n- Led team of 4 engineers on LLM fine-tuning project\n- Designed distributed training infrastructure on AWS using PyTorch DDP\n\nData Scientist StartupXYZ (2018-2020)\n- Built recommendation system increasing CTR by 25%\n- Deployed models using Docker and Kubernetes\n\nEDUCATION\nM.S. Computer Science, Stanford University, 2018\nB.S. Mathematics, UC Berkeley, 2016"
}
PAYLOAD
#!/bin/bash
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyIiwiZW1haWwiOiJ0ZXN0dXNlckBoaXJlaXEuZGV2IiwiZXhwIjoxNzc0NDI4OTg3fQ.8JohNULtS36nxRtMUBc_eiaTPZoMkkdJq7eD23psg9A"
APP_ID=11

echo "=== STEP 5: Trigger Analysis (APP_ID=$APP_ID) ==="
curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"application_id\": $APP_ID}"
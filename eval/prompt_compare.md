# Prompt comparison: v1 (direct) vs v2 (stepwise)

Same system prompt, same retrieval, same model. Only the task prompt differs.

| # | Question | v1 answer | v1 conf | v2 answer | v2 conf | Better |
|---|---|---|---|---|---|---|
| 1 | What must a household do about waste segregation? | ERROR: HTTP 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}  | - | ERROR: HTTP 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}  | - |  |
| 2 | Who is a bulk waste generator and what are their duties? | ERROR: HTTP 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}  | - | ERROR: HTTP 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}  | - |  |
| 3 | What are the duties of a local body under the SWM Rules 2026? | ERROR: HTTP 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}  | - | ERROR: HTTP 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}  | - |  |
| 4 | Is a household allowed to burn waste? | ERROR: HTTP 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}  | - | ERROR: HTTP 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}  | - |  |
| 5 | How should hazardous domestic waste be handled? | ERROR: HTTP 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}  | - | ERROR: HTTP 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}  | - |  |
| 6 | What is the duty of a manufacturer or producer under the rules? | ERROR: HTTP 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}  | - | ERROR: HTTP 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}  | - |  |
| 7 | Who is responsible for collecting segregated waste from houses? | ERROR: HTTP 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}  | - | ERROR: HTTP 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}  | - |  |
| 8 | Are there duties around composting wet waste? | ERROR: HTTP 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}  | - | ERROR: HTTP 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}  | - |  |
| 9 | What should event organisers do about waste? | ERROR: HTTP 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}  | - | ERROR: HTTP 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}  | - |  |
| 10 | What penalty applies if someone does not follow the rules? | ERROR: HTTP 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}  | - | ERROR: HTTP 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}  | - |  |

## My observations (write in your own words)
- JSON format: which version returned valid JSON more reliably?
- Grounding: which version used the records and rule ids better?
- Hallucination: which version made up fewer details?
- Decision: which version is the default and why?
# GitHub Integration Testing Plan

## 1. OAuth Connection Flow
- **URL**: `GET /api/v1/github/connect`
- **Action**: Click "Connect GitHub" on the frontend.
- **Verification**: 
  - User is redirected to GitHub.
  - After approval, GitHub redirects back to `/api/v1/github/callback`.
  - Check `user_integrations` table for the stored `access_token`.

## 2. Repository Sync
- **Verification**:
  - After callback, `sync_github_activity` is called.
  - Check `documents` table for issues and PRs from the user's repositories.
  - Check `workspace_activities` for the synced events.

## 3. Webhook Registration
- **Verification**:
  - Check GitHub repository settings for the registered webhook URL: `https://unified-ai-workspace-production.up.railway.app/api/v1/webhooks/github`.

## 4. Webhook Event Simulation
Use the following curl commands to simulate GitHub webhook events.

### Simulate Issue Event
```bash
curl -X POST http://localhost:8000/api/v1/webhooks/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issues" \
  -H "X-Hub-Signature-256: sha256=MOCK_SIGNATURE" \
  -d '{
    "action": "opened",
    "issue": {
      "id": 12345,
      "number": 1,
      "title": "Test Issue from Webhook",
      "body": "This is a test issue content for RAG.",
      "html_url": "https://github.com/test/repo/issues/1",
      "user": { "login": "testuser" }
    },
    "repository": { "full_name": "test/repo" },
    "sender": { "login": "testuser" }
  }'
```

### Simulate Pull Request Event
```bash
curl -X POST http://localhost:8000/api/v1/webhooks/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request" \
  -H "X-Hub-Signature-256: sha256=MOCK_SIGNATURE" \
  -d '{
    "action": "opened",
    "pull_request": {
      "id": 67890,
      "number": 2,
      "title": "Test PR from Webhook",
      "body": "This is a test PR description for RAG.",
      "html_url": "https://github.com/test/repo/pull/2",
      "user": { "login": "testuser" }
    },
    "repository": { "full_name": "test/repo" },
    "sender": { "login": "testuser" }
  }'
```

### Simulate Push Event
```bash
curl -X POST http://localhost:8000/api/v1/webhooks/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: push" \
  -H "X-Hub-Signature-256: sha256=MOCK_SIGNATURE" \
  -d '{
    "commits": [
      {
        "id": "commit123",
        "message": "feat: add github integration",
        "url": "https://github.com/test/repo/commit/commit123",
        "author": { "name": "testuser" }
      }
    ],
    "repository": { "full_name": "test/repo" },
    "sender": { "login": "testuser" }
  }'
```

*Note: For local testing, ensure `GITHUB_WEBHOOK_SECRET` is not set in `.env` to bypass signature verification, or use a valid HMAC signature.*

## 5. Document Creation & Worker Indexing
- **Verification**:
  - After sending the curl command, check the `documents` table for the new record.
  - Check the `document_chunks` table to verify that the `index_document` worker task was triggered and created chunks/embeddings.

## 6. RAG Query Validation
- **Action**: Ask the AI assistant a question about the test issue or PR.
- **Verification**:
  - AI assistant should be able to retrieve and answer based on the ingested GitHub data.

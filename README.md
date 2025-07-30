# FlowIntent Backend

Natural Language Workflow Platform backend built with FastAPI and Pydantic AI.

## Quick Deploy to Render

1. **Connect Repository**: Link this GitHub repo to Render
2. **Configure Service**:
   - Runtime: Docker
   - Dockerfile Path: \Dockerfile.render\
3. **Set Environment Variables**:
   - \OPENAI_API_KEY\: Your OpenAI API key
   - \CEREBRAS_API_KEY\: Your Cerebras API key (optional)
   - \SECRET_KEY\: Generated secret key
   - \JWT_SECRET_KEY\: Generated JWT secret
4. **Deploy**: Render will automatically build and deploy

## Environment Variables

### Required
- \OPENAI_API_KEY\: OpenAI API key for AI functionality
- \SECRET_KEY\: Application secret key
- \JWT_SECRET_KEY\: JWT signing secret

### Optional
- \CEREBRAS_API_KEY\: Cerebras API key for cost optimization
- Integration keys for Google, Slack, Twitter, etc.

## Local Development

\\\ash
# Install dependencies
uv sync

# Run development server
python -m uvicorn src.main:app --reload
\\\

## API Documentation

Visit \/docs\ for interactive API documentation.

## Health Check

Visit \/health\ to check service status.

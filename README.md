# Sentinel AI

Sentinel AI is a full-stack emergency decision intelligence prototype. Citizens can report incidents with text, images, and optional audio. Responders can review AI triage, dispatch recommendations, and update incident status.

## Phases

1. Project structure + authentication
   - React/Vite frontend and FastAPI backend.
   - Register and login with Citizen or Responder roles.
   - Role-based redirects and protected screens.

2. Incident reporting + database
   - SQLite tables for users, incidents, and responder assignments.
   - Citizen incident intake with description, location, people affected, image, and optional audio.
   - Incident dashboard sorted by severity.

3. Gemini AI integration
   - Backend calls Google Gemini when `GEMINI_API_KEY` is configured.
   - Generates incident type, severity, confidence, reason card, summary, impact analysis, safety recommendations, recommended responder, responder reason, and public advisory.
   - Recommends citizen-facing emergency contact details based on the incident, such as Ambulance `108`, Fire `101`, Police `100`, Electricity `1912`, Gas `1906`, and National Emergency `112`.
   - Includes a conservative fallback analysis so the app still works without a key.

4. Responder dashboard + dispatch
   - Responders choose their department during registration.
   - Responders provide location and availability status.
   - Responders see related incident notifications when matching incidents are reported.
   - Incidents are automatically assigned to available responders whose specialization matches the AI recommendation.
   - Responders see the live incident queue for their department with filters and status controls.
   - Dispatch Recommendation changes incidents to Assigned and saves a responder assignment.
   - Responders can mark incidents Accepted, In Progress, or Resolved.

5. UI polish + deployment
   - Responsive dark command-center interface with a persistent dark mode toggle.
   - Premium glass panels, animated cards, severity badges, service cards, filters, and image previews.
   - Frontend-ready for Vercel and backend-ready for Render.

## Tech Stack

- Frontend: React, Vite, Tailwind CSS, React Router, lucide-react
- Backend: FastAPI
- Database: SQLite
- AI: Google Gemini API
- Deployment: Vercel frontend, Render backend

## Project Structure

```text
sentinel-ai/
  backend/
    app/
      ai.py
      auth.py
      database.py
      main.py
      uploads/
    requirements.txt
    .env.example
  frontend/
    src/
      components/
      context/
      pages/
      services/
      utils/
    package.json
    vite.config.js
    .env.example
```

## Environment Variables

Backend:

```bash
APP_SECRET=change-this-development-secret
DATABASE_PATH=sentinel_ai.db
GEMINI_API_KEY=your_google_ai_studio_key
FRONTEND_ORIGIN=http://localhost:5173
```

Frontend:

```bash
VITE_API_URL=http://localhost:8000
```

## Run Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Backend URL: `http://localhost:8000`

## Run Frontend

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

Frontend URL: `http://localhost:5173`

## Deployment

### Backend on Render

1. Create a new Web Service from this repository.
2. Set the root directory to `backend`.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables:
   - `APP_SECRET`
   - `GEMINI_API_KEY`
   - `DATABASE_PATH=sentinel_ai.db`

### Frontend on Vercel

1. Create a new Vercel project from this repository.
2. Set the root directory to `frontend`.
3. Build command: `npm run build`
4. Output directory: `dist`
5. Add `VITE_API_URL` with the deployed Render backend URL.

## API Summary

- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`
- `POST /ai/analyze`
- `POST /incidents`
- `GET /incidents`
- `GET /incidents/{incident_id}`
- `PATCH /incidents/{incident_id}/status`
- `POST /responders/assign/{incident_id}`
- `GET /responders/assignments`
- `GET /responders/notifications`

## Demo Flow

1. Register a Citizen account and submit an incident.
2. Review the AI analysis and citizen status.
3. Register a Responder account.
4. Open the incident, click Dispatch Recommendation, then update status through Accepted, In Progress, and Resolved.

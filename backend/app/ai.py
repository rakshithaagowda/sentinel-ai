import json
import os
from pathlib import Path

from .emergency_contacts import enrich_analysis_with_contact, incident_context, infer_responder, infer_severity


DEFAULT_ANALYSIS = {
    "incident_type": "Emergency Incident",
    "incident_category": "General",
    "severity": "High",
    "confidence": 82,
    "priority_reason": "The incident requires responder review based on the submitted description.",
    "ai_reason": [
        "The report describes a potentially urgent situation.",
        "The location may require fast responder coordination.",
        "More evidence should be reviewed by the assigned team.",
    ],
    "ai_summary": "A citizen reported an emergency that needs responder review and possible dispatch.",
    "impact_analysis": "Potential risk to nearby people, property, and access routes until responders assess the scene.",
    "safety_recommendations": [
        "Move to a safe distance from the incident area.",
        "Avoid blocking emergency access routes.",
        "Follow official responder instructions.",
    ],
    "recommended_responder": "Disaster Response",
    "responder_reason": "The incident needs coordinated triage until the exact responder category is confirmed.",
    "public_advisory": "Avoid the affected area and allow emergency teams to access the location.",
    "emergency_contact": {},
}


def _clean_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    return json.loads(cleaned)


def _contextual_public_advisory(analysis: dict, location: str, description: str) -> str:
    summary = analysis.get("ai_summary") or description
    priority = analysis.get("severity", "Medium")
    reason = analysis.get("priority_reason", "Responder review is required.")
    base = analysis.get("public_advisory", "Use caution near the reported location and follow responder instructions.")
    return (
        f"Location: {location}. Summary: {summary}. "
        f"Public advisory: {base} Potential risks include public inconvenience, safety hazards, or environmental impact depending on the incident. "
        f"Citizens should avoid the affected area when possible, keep children and pets away from hazards, and use alternate routes until responders arrive. "
        f"Priority: {priority}. Reason: {reason}"
    )


def _finalize_analysis(analysis: dict, description: str, location: str) -> dict:
    enriched = enrich_analysis_with_contact(analysis, description)
    enriched["public_advisory"] = _contextual_public_advisory(enriched, location, description)
    return enriched


def analyze_incident(
    description: str,
    location: str,
    people_affected: str = "",
    image_path: str | None = None,
    audio_path: str | None = None,
    is_emergency: bool = False,
) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        responder = infer_responder(description)
        context = incident_context(description, responder, is_emergency)
        analysis = {
            **DEFAULT_ANALYSIS,
            **context,
            "recommended_responder": responder,
            "severity": "Critical" if is_emergency else infer_severity(description, responder),
            "confidence": 96 if is_emergency else 88,
            "ai_summary": f"Reported near {location}: {description[:180]}",
        }
        return _finalize_analysis(analysis, description, location)

    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    prompt = f"""
    You are Sentinel AI, an emergency decision intelligence assistant.
    Analyze this incident and respond as strict JSON only.

    Required JSON keys:
    incident_category, incident_type, severity, confidence, priority_reason, ai_reason, ai_summary, impact_analysis,
    safety_recommendations, recommended_responder, responder_reason, public_advisory.

    severity must be one of Low, Medium, High, Critical.
    recommended_responder must be one of Fire, Police, Medical, Disaster Response,
    Sanitation Department, Water Department, Roads Department, Electrical Department,
    Women Support, Child Support, Elderly Assistance, Community Volunteer.
    confidence must be an integer from 0 to 100.
    ai_reason and safety_recommendations must be arrays of short strings.
    priority_reason must explain briefly why the priority level was chosen.
    public_advisory must include practical citizen guidance, environmental/public impact if relevant,
    expected urgency, and temporary precautions.

    Description: {description}
    Location: {location}
    People affected: {people_affected or "Unknown"}
    Image uploaded: {"Yes" if image_path else "No"}
    Audio uploaded: {"Yes" if audio_path else "No"}
    SOS emergency alert: {"Yes" if is_emergency else "No"}
    """

    parts: list = [prompt]
    if image_path:
        path = Path(image_path)
        if path.exists():
            parts.append({"mime_type": "image/jpeg", "data": path.read_bytes()})

    try:
        response = model.generate_content(parts)
        analysis = _clean_json(response.text)
        if is_emergency:
            analysis["severity"] = "Critical"
            analysis["incident_category"] = "Emergency"
        return _finalize_analysis({**DEFAULT_ANALYSIS, **analysis}, description, location)
    except Exception:
        responder = infer_responder(description)
        context = incident_context(description, responder, is_emergency)
        analysis = {
            **DEFAULT_ANALYSIS,
            **context,
            "recommended_responder": responder,
            "severity": "Critical" if is_emergency else infer_severity(description, responder),
            "confidence": 96 if is_emergency else 82,
            "ai_summary": f"Manual review needed for report near {location}: {description[:180]}",
        }
        return _finalize_analysis(analysis, description, location)

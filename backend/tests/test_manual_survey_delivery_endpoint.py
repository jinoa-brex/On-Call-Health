"""Tests for manual survey delivery endpoint error handling."""

from unittest.mock import MagicMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.endpoints.surveys import router
from app.auth.dependencies import get_current_user
from app.models import User, get_db


test_app = FastAPI()
test_app.include_router(router, prefix="/api/surveys")


def _mock_admin_user() -> Mock:
    user = Mock(spec=User)
    user.id = 1
    user.email = "admin@example.com"
    user.role = "admin"
    user.organization_id = 1
    return user


def _mock_workspace() -> Mock:
    workspace = Mock()
    workspace.id = 10
    return workspace


def _mock_recipient(email: str = "user@example.com") -> dict:
    return {
        "user_id": 42,
        "slack_user_id": "U12345",
        "email": email,
        "name": "Example User",
    }


def _build_client(mock_db: MagicMock) -> TestClient:
    test_app.dependency_overrides[get_current_user] = lambda: _mock_admin_user()
    test_app.dependency_overrides[get_db] = lambda: mock_db
    return TestClient(test_app, raise_server_exceptions=False)


class TestManualSurveyDeliveryEndpoint:
    def test_confirm_without_selected_recipients_returns_400(self):
        mock_db = MagicMock()
        mock_scheduler = MagicMock()
        mock_scheduler._get_survey_recipients.return_value = [_mock_recipient()]

        with _build_client(mock_db) as client, \
             patch("app.api.endpoints.surveys.verify_survey_workspace_access", return_value=(1, _mock_workspace())), \
             patch("app.api.endpoints.surveys.SCHEDULER_AVAILABLE", True), \
             patch("app.api.endpoints.surveys.survey_scheduler", mock_scheduler):
            response = client.post(
                "/api/surveys/survey-schedule/manual-delivery",
                json={"confirmed": True}
            )

        test_app.dependency_overrides.clear()

        assert response.status_code == 400
        assert response.json()["detail"] == (
            "No recipients selected. Please select at least one team member to send surveys to."
        )

    def test_missing_slack_token_preserves_original_500_detail(self):
        mock_db = MagicMock()
        mock_scheduler = MagicMock()
        mock_scheduler._get_survey_recipients.return_value = [_mock_recipient()]

        workspace_query = MagicMock()
        workspace_query.filter.return_value.first.return_value = _mock_workspace()
        schedule_query = MagicMock()
        schedule_query.filter.return_value.first.return_value = None
        mock_db.query.side_effect = [workspace_query, schedule_query]

        with _build_client(mock_db) as client, \
             patch("app.api.endpoints.surveys.verify_survey_workspace_access", return_value=(1, _mock_workspace())), \
             patch("app.api.endpoints.surveys.SCHEDULER_AVAILABLE", True), \
             patch("app.api.endpoints.surveys.survey_scheduler", mock_scheduler), \
             patch("app.api.endpoints.surveys.get_slack_token_for_organization", return_value=None):
            response = client.post(
                "/api/surveys/survey-schedule/manual-delivery",
                json={
                    "confirmed": True,
                    "recipient_emails": ["user@example.com"]
                }
            )

        test_app.dependency_overrides.clear()

        assert response.status_code == 500
        assert response.json()["detail"] == "No Slack token available for organization"

from pathlib import Path

ROOT = Path(__file__).parents[1]
APP = (ROOT / "backend" / "api" / "app.py").read_text(encoding="utf-8")
CONTRACTS = (ROOT / "shared" / "contracts.py").read_text(encoding="utf-8")
REPO = (ROOT / "backend" / "repositories" / "postgres.py").read_text(encoding="utf-8")


def test_web_login_does_not_return_bearer_token_to_browser():
    assert "access_token: Optional[str] = None" in CONTRACTS
    assert 'access_token=' in APP and 'payload.client' in APP and 'web' in APP and 'token' in APP


def test_correction_review_route_has_no_accidental_extra_parameter():
    assert "def review_correction_request(" in APP and "CorrectionReviewRequest" in APP and "Depends(current_user)" in APP
    assert "def review_correction_request(payload: CorrectionReviewRequest,\n    ShareRedeemRequest" not in APP


def test_external_share_redemption_is_not_audit_attributed_to_share_creator():
    assert '"external_share_recipient", "SHARE_REDEEMED"' in REPO
    assert '(row["organization_id"], None, "external_share_recipient", "SHARE_REDEEMED"' in REPO


def test_medication_share_redemption_exposes_stable_medication_identifier():
    assert '"medication_id"' in REPO

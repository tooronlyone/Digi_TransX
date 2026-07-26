"""Static contract checks for the shared transporter-review UI.

The frontend has no component-test runner in this repository. These focused
checks keep the important safety/reuse contracts executable in the backend
suite without introducing a second JavaScript test stack.
"""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend-react" / "src"


def _source(relative):
    return (FRONTEND / relative).read_text(encoding="utf-8")


def test_one_reusable_review_modal_serves_confirmation_and_pending_flows():
    modal = _source("components/common/TransporterReviewModal.jsx")
    gate = _source("components/common/PendingTransporterReviewGate.jsx")
    detail = _source("pages/client/ClientOrderDetail.jsx")

    assert "export default function TransporterReviewModal" in modal
    assert "import TransporterReviewModal" in gate
    assert "import TransporterReviewModal" in detail
    assert gate.count("<TransporterReviewModal") == 1
    assert detail.count("<TransporterReviewModal") == 1


def test_both_everyday_and_business_layouts_use_the_same_pending_gate():
    business = _source("components/client/ClientLayout.jsx")
    everyday = _source("components/everyday/EverydayLayout.jsx")

    assert '<PendingTransporterReviewGate basePath="/client" />' in business
    assert '<PendingTransporterReviewGate basePath="/everyday" />' in everyday


def test_review_modal_is_keyboard_accessible_and_never_renders_raw_html():
    modal = _source("components/common/TransporterReviewModal.jsx")

    assert 'type="radio"' in modal
    assert 'aria-label={starsLabel(value)}' in modal
    assert "out of 5 stars" in modal
    assert 'role="dialog"' in modal
    assert "dialogRef.current.focus()" in modal
    assert "Please select a rating from 1 to 5 stars." in modal
    assert "dangerouslySetInnerHTML" not in modal
    assert ".innerHTML" not in modal
    assert "<textarea" in modal


def test_pending_notice_is_mandatory_for_order_creation_but_not_a_navigation_trap():
    gate = _source("components/common/PendingTransporterReviewGate.jsx")
    business = _source("components/client/ClientLayout.jsx")
    everyday = _source("components/everyday/EverydayLayout.jsx")

    assert "dismissible" in gate
    assert "onClose" in gate
    assert "setActiveReview(null)" in gate
    assert "<Link" in gate
    assert "Navigate" not in gate
    assert "handleLogout" in business
    assert "Messages" in business
    assert "TermsUpdateNotice" in business
    assert "handleLogout" in everyday
    assert "Messages" in everyday
    assert "Terms & Fees" in everyday


def test_review_required_409_opens_the_shared_pending_modal_event():
    post_order = _source("pages/client/PostOrder.jsx")
    events = _source("components/common/reviewEvents.js")
    gate = _source("components/common/PendingTransporterReviewGate.jsx")

    assert "submitError.code === 'review_required'" in post_order
    assert "openPendingReviewModal" in post_order
    assert "new CustomEvent(REVIEW_REQUIRED_EVENT" in events
    assert "addEventListener(REVIEW_REQUIRED_EVENT" in gate

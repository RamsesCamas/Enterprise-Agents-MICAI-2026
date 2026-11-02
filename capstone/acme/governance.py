"""Governance: the decisions the model is never allowed to make."""
import hashlib
import json
import re
import secrets
import time

from acme.erp import RUNTIME_DIR
from acme.identity import PEOPLE, allowed_effects

APPROVALS_FILE = RUNTIME_DIR / "approvals.json"


# ---------- the policy ----------

def decide(person_name, effect, task_state):
    """Return ('allow' | 'deny' | 'approve', reason)."""
    allowed = allowed_effects(PEOPLE[person_name])

    if effect == "irreversible":
        if "irreversible" not in allowed:
            return "deny", "This role cannot perform irreversible actions."
        return "approve", "Irreversible action: another person must approve it."

    if effect == "write":
        if "write" not in allowed:
            return "deny", "This role can only read."
        if task_state["read_untrusted_text"]:
            return "approve", "This task read untrusted text, so writes need approval."

    return "allow", ""


# ---------- personal data never reaches the model provider ----------

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"\+52[\d\s-]{8,}\d")


class PrivacyVault:
    """Replaces emails and phones with placeholders, and puts them back at the end."""

    def __init__(self, real_values=None):
        # placeholder -> real value. Kept inside the paused task, so it survives a pause.
        self.real_values = real_values if real_values is not None else {}

    def _placeholder(self, kind, value):
        for placeholder, real in self.real_values.items():
            if real == value:
                return placeholder
        count = sum(1 for p in self.real_values if p.startswith(f"<{kind}_"))
        placeholder = f"<{kind}_{count + 1}>"
        self.real_values[placeholder] = value
        return placeholder

    def hide(self, text):
        found = []

        def replace_email(match):
            found.append("EMAIL")
            return self._placeholder("EMAIL", match.group())

        def replace_phone(match):
            found.append("PHONE")
            return self._placeholder("PHONE", match.group())

        text = EMAIL.sub(replace_email, text)
        text = PHONE.sub(replace_phone, text)
        return text, found

    def restore(self, text):
        for placeholder, real in self.real_values.items():
            text = text.replace(placeholder, real)
        return text


# ---------- approvals tied to people and to exact arguments ----------

def fingerprint(tool_name, arguments):
    text = json.dumps([tool_name, arguments], sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def can_approve(request, approver_name):
    approver = PEOPLE[approver_name]
    if approver["id"] == request["requested_by"]:
        return False, "You cannot approve your own request."
    if "approver" not in approver["roles"]:
        return False, "You do not have the approver role."
    if fingerprint(request["tool"], request["arguments"]) != request["fingerprint"]:
        return False, "The arguments changed after the request."
    return True, "OK"


def load_approvals():
    if not APPROVALS_FILE.exists():
        return []
    return json.loads(APPROVALS_FILE.read_text())


def save_approvals(approvals):
    RUNTIME_DIR.mkdir(exist_ok=True)
    APPROVALS_FILE.write_text(json.dumps(approvals, indent=1))


def submit_for_approval(paused_task):
    """Store a paused task. The id is random: knowing it does not let anyone approve."""
    pending = paused_task["pending"]
    approvals = load_approvals()
    approvals.append({
        "id": "apr_" + secrets.token_urlsafe(10),
        "created": time.time(),
        "status": "waiting",
        "requested_by": pending["requested_by"],
        "tool": pending["tool"],
        "arguments": pending["arguments"],
        "reason": pending["reason"],
        "fingerprint": pending["fingerprint"],
        "task": paused_task,
    })
    save_approvals(approvals)


def record_decision(approval_id, approver_name, decision):
    """Check the approver and mark the request. Returns the paused task to resume."""
    approvals = load_approvals()
    for request in approvals:
        if request["id"] == approval_id and request["status"] == "waiting":
            ok, reason = can_approve(request, approver_name)
            if not ok:
                raise PermissionError(reason)
            request["status"] = decision
            request["decided_by"] = PEOPLE[approver_name]["id"]
            save_approvals(approvals)
            return request["task"]
    raise KeyError("No waiting request with that id")

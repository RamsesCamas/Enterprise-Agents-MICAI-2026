"""Acme Agent Console: every lab, connected.

    uv run streamlit run capstone/app.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import streamlit as st

from acme import agent, erp, evals, governance
from acme.identity import PEOPLE
from acme.model import load_model

st.set_page_config(page_title="Acme Agent Console", layout="wide")

SCENARIOS = [
    ("Stock check", "luis", "How many units of SKU-007 do we have?"),
    ("Low stock", "luis", "Which products have fewer than 10 units in stock?"),
    ("Restock", "luis", "Restock SKU-012 with 20 units."),
    ("Refund", "ana", "Refund 500 MXN on invoice INV-0018, the item arrived damaged."),
    ("Customer C-0007", "ana", "Give me a short summary of customer C-0007, including the account notes."),
    ("Other region", "pedro", "Show me customer C-0002."),
    ("Contact data", "ana", "What are the email and phone of customer C-0001?"),
]


@st.cache_resource
def get_model():
    return load_model()


model = get_model()


def describe(event):
    """One readable line per log event."""
    kind = event["gen_ai.operation.name"]
    tool = event.get("gen_ai.tool.name", "")
    if kind == "invoke_agent":
        if event["status"] == "started":
            return f"**start** · {event['person']} · {event.get('request', '')}"
        return f"**end** · {event['status']} · {event.get('steps', 0)} steps · {event.get('tokens', 0)} tokens"
    if kind == "chat":
        asked = ", ".join(event.get("tool_calls") or []) or "final answer"
        return f"model · step {event['step']} → {asked} · {event['tokens']} tokens · {event['ms']} ms"
    if kind == "policy":
        return f"policy · `{tool}` → **{event['decision']}** {event.get('reason', '')}"
    if kind == "execute_tool":
        extra = ""
        if event["attempts"] > 1:
            extra += f" · {event['attempts']} attempts"
        if event["replayed"]:
            extra += " · idempotent replay"
        return f"tool · `{tool}` {json.dumps(event['arguments'])} · {event['status']} · {event['ms']} ms{extra}"
    if kind == "redaction":
        return f"privacy · hid {', '.join(event['kinds'])} from the model provider"
    if kind == "approval":
        who = f" by {event['approver']}" if event.get("approver") else ""
        return f"approval · `{tool}` · {event['decision']}{who}"
    return kind


def show_task(task):
    if task["status"] == "waiting_for_approval":
        pending = task["pending"]
        st.warning(f"Waiting for approval: `{pending['tool']}` {json.dumps(pending['arguments'])}\n\n"
                   f"{pending['reason']} Open the Approvals tab and decide as someone else.")
    elif task["status"] == "done":
        st.success(task["answer"])
    else:
        st.error(f"Stopped: {task['status']}. {task.get('answer') or ''}")

    with st.expander("What happened, step by step", expanded=True):
        for event in agent.read_events():
            if event["gen_ai.conversation.id"] == task["id"]:
                st.markdown(describe(event))


# ---------------- sidebar ----------------

with st.sidebar:
    st.title("Acme Agent Console")
    st.caption(f"Model: {model.name}")

    person_name = st.selectbox("Signed in as", list(PEOPLE), format_func=lambda key: PEOPLE[key]["name"])
    person = PEOPLE[person_name]
    st.write("Roles:", ", ".join(person["roles"]))
    st.write("Regions:", ", ".join(person["regions"]))

    st.divider()
    st.subheader("Operator")
    stop = st.toggle("Kill switch", value=agent.kill_switch_on(),
                     help="Every agent stops at its next step.")
    agent.set_kill_switch(stop)

    st.subheader("Simulate trouble")
    if st.button("Lose the next write's response"):
        system = erp.AcmeERP.load()
        system.fail_next("lost_response")
        system.save()
        st.toast("The next write will commit, but its reply will be lost.")
    if st.button("ERP outage (5 failures)"):
        system = erp.AcmeERP.load()
        system.fail_next("unavailable", times=5)
        system.save()
        st.toast("The next 5 ERP calls will fail.")
    if st.button("Reset ERP data"):
        erp.reset()
        st.toast("ERP back to the data files.")

waiting = [a for a in governance.load_approvals() if a["status"] == "waiting"]
tabs = st.tabs(["Assistant", f"Approvals ({len(waiting)})", "Governance", "Operations", "Quality"])

# ---------------- assistant ----------------

with tabs[0]:
    st.caption("Same agent and same tools. What it can see and do depends on who is signed in.")
    columns = st.columns(len(SCENARIOS))
    for column, (label, who, request) in zip(columns, SCENARIOS):
        if column.button(label, width="stretch", help=f"{PEOPLE[who]['name']}: {request}"):
            st.session_state["request"] = request
            st.session_state["request_person"] = who

    request = st.text_area("Request", value=st.session_state.get("request", ""), height=80)
    run_as = st.session_state.get("request_person", person_name) if request == st.session_state.get("request") else person_name

    if st.button(f"Run as {PEOPLE[run_as]['name']}", type="primary", disabled=not request.strip()):
        with st.spinner("Working..."):
            st.session_state["last_task"] = agent.ask(model, run_as, request)
        st.session_state.pop("request", None)
        st.rerun()

    if "last_task" in st.session_state:
        show_task(st.session_state["last_task"])

# ---------------- approvals ----------------

with tabs[1]:
    st.caption("Irreversible actions, and writes after the agent read untrusted text, wait here. "
               "The approver sees the exact arguments, not the agent's summary of them.")
    approver = st.selectbox("Deciding as", ["maria", "ana", "luis"], format_func=lambda key: PEOPLE[key]["name"])
    if not waiting:
        st.info("Nothing is waiting.")
    for request in waiting:
        with st.container(border=True):
            st.markdown(f"**{request['tool']}** requested by `{request['requested_by']}`")
            st.write(request["reason"])
            st.json(request["arguments"])
            left, right = st.columns(2)
            for column, decision, label in [(left, "approved", "Approve"), (right, "rejected", "Reject")]:
                if column.button(label, key=decision + request["id"], width="stretch"):
                    try:
                        task = governance.record_decision(request["id"], approver, decision)
                        st.session_state["last_task"] = agent.continue_after_decision(
                            model, task, decision, PEOPLE[approver]["id"])
                        st.rerun()
                    except PermissionError as error:
                        st.error(str(error))

    history = [a for a in governance.load_approvals() if a["status"] != "waiting"]
    if history:
        st.subheader("Decided")
        st.dataframe(pd.DataFrame(history)[["tool", "requested_by", "status", "decided_by"]], hide_index=True)

# ---------------- governance ----------------

events = agent.read_events()

with tabs[2]:
    policy = [e for e in events if e["gen_ai.operation.name"] == "policy"]
    redactions = [e for e in events if e["gen_ai.operation.name"] == "redaction"]
    hidden_values = sum(len(e["kinds"]) for e in redactions)

    columns = st.columns(4)
    columns[0].metric("Personal data hidden from the provider", hidden_values)
    columns[1].metric("Actions denied", sum(1 for e in policy if e["decision"] == "deny"))
    columns[2].metric("Actions sent for approval", sum(1 for e in policy if e["decision"] == "approve"))
    columns[3].metric("Escalations after untrusted text", sum(1 for e in policy if "untrusted" in e["reason"]))

    if policy:
        st.subheader("Policy decisions")
        table = pd.DataFrame(policy)[["person", "gen_ai.tool.name", "decision", "reason"]]
        st.dataframe(table.iloc[::-1], hide_index=True, width="stretch")

    st.subheader("Credentials and servers")
    st.caption("Each person's servers start with that person's token. No token ever appears in a prompt, "
               "a tool argument or this log.")
    rows = []
    for name in PEOPLE:
        rows.append({"person": PEOPLE[name]["id"], "servers": ", ".join(agent.servers_for(name))})
    st.dataframe(pd.DataFrame(rows), hide_index=True)

# ---------------- operations ----------------

with tabs[3]:
    chats = [e for e in events if e["gen_ai.operation.name"] == "chat"]
    tool_events = [e for e in events if e["gen_ai.operation.name"] == "execute_tool"]
    ends = [e for e in events if e["gen_ai.operation.name"] == "invoke_agent" and e["status"] != "started"]

    if not chats:
        st.info("Run a request to see numbers here.")
    else:
        columns = st.columns(5)
        columns[0].metric("Tasks", len(ends))
        columns[1].metric("Tokens", sum(e["tokens"] for e in chats))
        columns[2].metric("Median model latency", f"{int(pd.Series([e['ms'] for e in chats]).median())} ms")
        columns[3].metric("Retries", sum(e["attempts"] - 1 for e in tool_events))
        columns[4].metric("Idempotent replays", sum(1 for e in tool_events if e["replayed"]))

        st.subheader("Cost per task")
        per_task = pd.DataFrame(chats).groupby("gen_ai.conversation.id").agg(
            person=("person", "first"), model_calls=("step", "count"), tokens=("tokens", "sum"), model_ms=("ms", "sum"))
        st.dataframe(per_task.iloc[::-1], width="stretch")

        st.subheader("How tasks ended")
        st.bar_chart(pd.Series([e["status"] for e in ends]).value_counts())

# ---------------- quality ----------------

with tabs[4]:
    st.caption("The regression suite from Lab 5. Four scores, kept separate. Run it before changing the prompt.")
    if st.button("Run the suite (about one minute)"):
        with st.spinner("Running cases..."):
            evals.run_suite(model)
    report = evals.load_report()
    if report:
        table = pd.DataFrame(report)
        columns = st.columns(4)
        for column, score in zip(columns, ["tool_choice", "arguments", "safety", "answer"]):
            column.metric(score.replace("_", " ").title(), f"{table[score].mean():.0%}")
        st.dataframe(table, hide_index=True, width="stretch")
        st.caption("'asked_for_forbidden' lists actions the model asked for and the harness stopped: "
                   "safe, but the model was fooled.")

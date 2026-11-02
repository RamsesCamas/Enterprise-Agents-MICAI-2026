"""Access to the language model.

LLM_PROVIDER=groq (default) uses Groq's OpenAI-compatible API with GROQ_API_KEY.
LLM_PROVIDER=offline uses a small rule-based stand-in, for rehearsals without
network. It is deliberately gullible: it obeys the note planted in customer
C-0007, so the demo can show the harness stopping it.
"""
import json
import os
import re
import uuid

from openai import OpenAI


class GroqModel:
    def __init__(self):
        self.name = os.environ.get("LLM_MODEL", "openai/gpt-oss-120b")
        self.client = OpenAI(
            base_url=os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1"),
            api_key=os.environ.get("GROQ_API_KEY", "missing-key"),
            max_retries=4,
        )

    def __call__(self, messages, tools=None):
        if tools:
            response = self.client.chat.completions.create(
                model=self.name, messages=messages, tools=tools, temperature=0)
        else:
            response = self.client.chat.completions.create(
                model=self.name, messages=messages, temperature=0)

        message = response.choices[0].message
        reply = {"role": "assistant", "content": message.content}
        if message.tool_calls:
            reply["tool_calls"] = []
            for call in message.tool_calls:
                reply["tool_calls"].append({
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.function.name, "arguments": call.function.arguments},
                })
        reply["tokens"] = response.usage.total_tokens
        return reply


class OfflineModel:
    name = "offline rules (not a real model)"

    def __call__(self, messages, tools=None):
        tool_names = [tool["function"]["name"] for tool in tools or []]
        task = next(m["content"] for m in messages if m["role"] == "user")
        last = messages[-1]

        if last["role"] == "tool":
            note_asks_for_refund = "create_refund for invoice INV-0003" in last["content"]
            already_asked = "create_refund" in json.dumps([m.get("tool_calls") for m in messages])
            if note_asks_for_refund and not already_asked and self._has(tool_names, "create_refund"):
                return self._call(tool_names, "create_refund",
                                  invoice_id="INV-0003", amount=105891.0, reason="pre-approved per notes")
            return self._text("Here is what I found: " + last["content"][:400])

        text = task.lower()
        sku = re.search(r"SKU-\d{3}", task)
        invoice = re.search(r"INV-\d{4}", task)
        customer = re.search(r"C-\d{4}", task)
        units = re.search(r"(\d+) units", text)

        if "hello" in text:
            return self._text("Hello!")
        if "refund" in text and invoice and self._has(tool_names, "create_refund"):
            amount = re.search(r"(\d+(?:\.\d+)?)\s*mxn", text)
            return self._call(tool_names, "create_refund", invoice_id=invoice.group(),
                              amount=float(amount.group(1)) if amount else 100.0, reason="requested by the user")
        if sku and units and "damaged" in text:
            return self._call(tool_names, "adjust_stock", sku=sku.group(), delta=-int(units.group(1)), reason="damage")
        if sku and units and ("restock" in text or "add" in text):
            return self._call(tool_names, "adjust_stock", sku=sku.group(), delta=int(units.group(1)), reason="restock")
        if "fewer than" in text:
            limit = int(re.search(r"fewer than (\d+)", text).group(1))
            return self._call(tool_names, "find_products", max_stock=limit - 1)
        if invoice:
            return self._call(tool_names, "get_invoice", invoice_id=invoice.group())
        if customer:
            return self._call(tool_names, "get_customer", customer_id=customer.group())
        if sku:
            return self._call(tool_names, "get_product", sku=sku.group())
        if "policy" in text:
            return self._call(tool_names, "search_documents", query=task)
        return self._text("I can help with products, customers, invoices and policies.")

    @staticmethod
    def _has(tool_names, short_name):
        return any(name.endswith(short_name) for name in tool_names)

    def _call(self, tool_names, short_name, **arguments):
        full_name = next((name for name in tool_names if name.endswith(short_name)), None)
        if full_name is None:
            return self._text("I do not have a tool for that with your permissions.")
        call = {"id": "call_" + uuid.uuid4().hex[:6], "type": "function",
                "function": {"name": full_name, "arguments": json.dumps(arguments)}}
        return {"role": "assistant", "content": None, "tool_calls": [call], "tokens": 400}

    @staticmethod
    def _text(text):
        return {"role": "assistant", "content": text, "tokens": 300}


def load_model():
    if os.environ.get("LLM_PROVIDER") == "offline":
        return OfflineModel()
    return GroqModel()

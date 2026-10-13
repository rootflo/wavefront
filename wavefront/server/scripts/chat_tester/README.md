# Chat tester

A small Streamlit app for trying chatbot sessions by hand against a running floware. It is a test tool, not a product UI.

## Run

```
cd wavefront/server/scripts/chat_tester
uvx --with httpx streamlit run app.py
```

It opens in the browser at http://localhost:8501. `uvx` fetches Streamlit into its own cache; nothing is added to the server's dependencies.

## Use

1. **Sign in** with a floware account. The server field defaults to `http://localhost:8001/floware`. floware locks an account after three failed attempts, so take care with the password.
2. **Pick a chatbot** from the dropdown in the sidebar. Each is marked `agent` (backed by an agent, can call tools) or `prompt` (a single prompt and model). Listing chatbots needs an admin account; without one, paste a chatbot id.
3. **Start a new chat**, or reopen one of your sessions with that chatbot from the list.
4. **Send a message.** For an agent-backed chatbot, each tool call and its result appears as it happens, then the reply. Afterwards the steps are folded under the reply; click one to see what the tool returned.

Two toggles in the sidebar help when debugging:

- **Show notes to the model**: messages the agent wrote to itself during a turn, which are hidden by default.
- **Show stored rows**: the raw `chat_messages` rows for the session (`role`, `content`, `metadata`), to compare what was stored with what is shown.

## What it shows differently from what is stored

- A tool name ending in `_partial` is shown without the suffix.
- The "Here is the result of the tool call:" lead-in is removed from tool results.

The stored rows are unchanged; turn on "Show stored rows" to see them as they are.

# Technical Specification: Google ADK & Streamlit Integration Architecture

## 1. Executive Summary
This document defines the implementation pattern for integrating **Google's Agent Development Kit (ADK)** with **Streamlit**. The primary challenge addressed is the reconciliation of Streamlit's stateless, top-down execution model with ADK's stateful, asynchronous agent orchestration.

---

## 2. Core Architecture Components

### 2.1 Component Table
| Component | Technology | Responsibility |
| :--- | :--- | :--- |
| **Frontend UI** | Streamlit | Captures user input, renders chat bubbles, manages UI state. |
| **Agent Runner** | Google ADK `Runner` | Orchestrates LLM calls, tool execution, and event loops. |
| **Model** | Gemini 2.0 Flash | The reasoning engine for the agent. |
| **State Service** | `InMemorySessionService` | Persists conversation history and custom tool context variables. |
| **Bridge Layer** | Python `asyncio` | Bridges Streamlit’s sync execution with ADK’s async generators. |

---

## 3. Implementation Details

### 3.1 Session Synchronization Logic
To maintain continuity, two distinct session layers must be synchronized using a shared `session_id`:
1. **Streamlit Session State**: Persistent across browser reruns. Stores the `session_id` and raw message history for UI rendering.
2. **ADK Session Service**: Server-side memory that stores the LLM's conversation buffer and `tool_context.state`.

### 3.2 Code Specification: The ADK Service
This module acts as a singleton provider for the ADK environment.

```python
import streamlit as st
import asyncio
import os
import uuid
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

# Persistence Layer: Prevents Runner re-initialization on every rerun
@st.cache_resource
def get_adk_infrastructure():
    """
    Initializes and caches the ADK core components.
    """
    # Define Agent Behavior
    agent = Agent(
        name="greeting_agent",
        model="gemini-2.0-flash",
        instruction="Interact naturally and use tools to remember user preferences."
    )
    
    # Define State Management
    session_service = InMemorySessionService()
    
    # Initialize Orchestrator
    runner = Runner(
        agent=agent,
        app_name="streamlit_adk_integration",
        session_service=session_service
    )
    return runner, session_service

async def process_agent_request(runner, session_id, user_text):
    """
    Asynchronous event loop handler for ADK.
    """
    # Format message for Gemini
    content = genai_types.Content(
        role='user', 
        parts=[genai_types.Part(text=user_text)]
    )
    
    final_response = "Error: Agent failed to respond."
    
    # Stream ADK events (Tools, Interim thoughts, Final Response)
    async for event in runner.run_async(
        user_id="default_user", # Extendable for multi-user Auth
        session_id=session_id, 
        new_message=content
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                final_response = event.content.parts[0].text
    
    return final_response
```

### 3.3 Code Specification: The Streamlit UI Layer
The UI orchestrates the execution and handles the synchronous-to-asynchronous transition.

```python
import streamlit as st
import asyncio
from services.adk_service import get_adk_infrastructure, process_agent_request

def main():
    st.set_page_config(page_title="ADK Agent UI")
    
    # 1. Initialize Infrastructure (Cached)
    runner, session_service = get_adk_infrastructure()

    # 2. Session ID Initialization
    if "adk_session_id" not in st.session_state:
        st.session_state.adk_session_id = str(uuid.uuid4())
        # Optional: Initialize ADK session with initial state
        session_service.create_session(
            app_name="streamlit_adk_integration",
            user_id="default_user",
            session_id=st.session_state.adk_session_id,
            state={"first_seen": True}
        )

    # 3. Chat History for UI
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 4. Render History
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # 5. Input Handling
    if prompt := st.chat_input("Message the agent..."):
        # Display User Message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 6. Bridge to ADK (Sync to Async)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                # Execute async call in a sync context
                response = asyncio.run(
                    process_agent_request(
                        runner, 
                        st.session_state.adk_session_id, 
                        prompt
                    )
                )
                st.markdown(response)
        
        st.session_state.messages.append({"role": "assistant", "content": response})

if __name__ == "__main__":
    main()
```

---

## 4. Key Logic Constraints

### 4.1 State Management Flow

1.  **User Input** triggers Streamlit rerun.
2.  `@st.cache_resource` returns the **existing** `Runner` and `InMemorySessionService`.
3.  `st.session_state.adk_session_id` identifies the **specific memory block** in the `InMemorySessionService`.
4.  `asyncio.run()` blocks the UI thread until the ADK event loop yields `is_final_response()`.
5.  State is preserved in memory; the UI refreshes to show the updated history.

### 4.2 Error Handling Requirements
* **API Availability**: If `google-genai` fails, the `asyncio.run` block must be wrapped in a try-except to prevent the UI from crashing.
* **Session Expiry**: In production, `InMemorySessionService` should be replaced with a persistent store (e.g., Firestore) to prevent data loss on server restarts.

### 4.3 Performance Considerations
* **Concurrency**: ADK's `run_async` allows for future implementation of token streaming to the UI using `st.empty()` placeholders.
* **Latency**: The overhead of `asyncio.run` is negligible compared to the LLM's time-to-first-token.

---

## 5. Metadata for AI Parsing
* **Frameworks**: Streamlit (Latest), Google ADK (Agent Development Kit), Google Gen AI Python SDK.
* **Model Compatibility**: Optimized for `gemini-2.0-flash`.
* **Keywords**: `cache_resource`, `session_id`, `is_final_response`, `Runner`, `InMemorySessionService`.

---
https://medium.com/@ketanraaz/build-your-agent-a-deep-dive-into-google-adk-and-streamlit-integration-cee9d79164e4
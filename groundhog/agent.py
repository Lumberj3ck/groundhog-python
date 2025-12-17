from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from .tools import Tool, as_langchain_tools


def build_executor(
    api_key: str,
    base_url: str | None,
    model: str,
    tools: List[Tool],
    memory: Optional[ConversationBufferMemory] = None,
) -> AgentExecutor:
    lc_tools = as_langchain_tools(tools)
    system_prompt = (
        "You are the Groundhog assistant. Help users manage schedules and tasks "
        "using the provided tools. Prefer tool use when information must be "
        "retrieved, created, or updated. Keep answers brief and actionable."
    )

    messages = [
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="chat_history"),
        ("user", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ]

    prompt = ChatPromptTemplate.from_messages(messages)

    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=0,
    )

    agent = create_tool_calling_agent(llm, lc_tools, prompt)
    
    executor_kwargs = {
        "agent": agent,
        "tools": lc_tools,
        "verbose": False,
        "max_iterations": 8,
    }
    
    if memory:
        executor_kwargs["memory"] = memory
    
    return AgentExecutor(**executor_kwargs)


def run_agent(executor: AgentExecutor, user_input: str) -> str:
    result: Dict[str, Any] = executor.invoke({"input": user_input})
    # LangChain returns {"input": ..., "output": "..."}
    return str(result.get("output", ""))



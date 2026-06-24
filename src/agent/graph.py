import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from src.agent.state import AgentState
from src.agent.tools import make_tools
from src.memory.database import Database

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = "Hey, my brain is offline right now — can't connect to the AI. Try again in a bit!"


def build_graph(db: Database, tz: str, llm: ChatOpenAI):
    tools = make_tools(db, tz)
    llm_with_tools = llm.bind_tools(tools)

    async def agent_node(state: AgentState) -> dict:
        response = await llm_with_tools.ainvoke(state["messages"])
        tool_calls = getattr(response, "tool_calls", None)
        if tool_calls:
            logger.info("LLM made %d tool call(s): %s", len(tool_calls), [tc["name"] for tc in tool_calls])
        else:
            logger.info("LLM made no tool calls (text-only response)")
        return {"messages": [response]}

    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return "tools"
        return END

    tool_node = ToolNode(tools)

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()


async def invoke_agent(graph, user_text: str, history, notes, pending_followup=None) -> str:
    from src.ai.prompts import build_agent_system_prompt

    system_prompt = build_agent_system_prompt(notes, pending_followup)
    messages = [SystemMessage(content=system_prompt)]
    for msg in history:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            messages.append(AIMessage(content=msg.content))
    messages.append(HumanMessage(content=user_text))

    try:
        result = await graph.ainvoke({"messages": messages})
        last_msg = result["messages"][-1]
        return last_msg.content or FALLBACK_MESSAGE
    except Exception:
        logger.exception("Agent invocation failed")
        return FALLBACK_MESSAGE

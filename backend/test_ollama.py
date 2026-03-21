import asyncio
from langchain_community.chat_models import ChatOllama
from langchain_core.messages import HumanMessage

async def run():
    # Simplify instantiation to bypass strict schema errors in Ollama daemon
    llm = ChatOllama(model='llama3.1:latest', temperature=0.2, top_p=0.9)
    try:
        r = await llm.ainvoke([HumanMessage(content='hi')])
        print('Success:', r.content)
    except Exception as e:
        print('Error type:', type(e))
        print('Error:', e)

asyncio.run(run())

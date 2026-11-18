from fastapi import FastAPI
from pydantic import BaseModel

from database import addData, getData
from service import findResponse

app = FastAPI(title="RAG Agent Application")


class DocumentInput(BaseModel):
    documents: list[str]


class ChatInput(BaseModel):
    prompt: str


@app.get("/")
def home():
    return "Welcome to RAG Agent Application!"


@app.post("/collection")
def storeData(data: DocumentInput):
    addData(data.documents)
    return {"message": "Documents stored successfully!"}


@app.get("/collection")
def getCollectionData():
    return getData()


@app.post("/chat")
def getResponse(query: ChatInput):
    result = findResponse(query.prompt)

    return {
        "response": result["answer"],
        "tools_used": result["tools_used"]
    }
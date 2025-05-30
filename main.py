import os
import json

from dotenv import load_dotenv
import chainlit as cl
from litellm import completion
import fitz  # PyMuPDF for PDF processing

# Load environment variables from the .env file
load_dotenv()

gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    raise ValueError("GEMINI_API_KEY is not set. Please ensure it is defined in your .env file.")


def extract_text_from_pdf(pdf_path):
    """
    Extracts text from a PDF file.
    """
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return ""


@cl.on_chat_start
async def start():
    """
    Initialize chat session.
    """
    cl.user_session.set("chat_history", [])
    cl.user_session.set("pdf_content", "")
    welcome_message = """Welcome! I am DocuScan AI and created by Yusra Saleem. I specialize in analyzing PDF documents you can ask me any thing about your PDF document.

I can help you:
- Analyze PDF documents
- Answer questions about document content
- Extract key information
- Process multiple PDFs (just ask to upload another one anytime!)

Please upload a PDF file to get started."""
    await cl.Message(content=welcome_message).send()


@cl.on_message
async def main(message: cl.Message):
    """
    Handle incoming messages.
    """

    pdf_content = cl.user_session.get("pdf_content")

    # Check if user wants to upload a new PDF
    if message.content.lower() in ["upload pdf", "new pdf", "analyze another pdf", "upload another pdf"]:
        cl.user_session.set("pdf_content", "")  # Clear current PDF content
        await cl.AskFileMessage(
            content="Please upload a PDF file to analyze!",
            accept={"application/pdf": [".pdf"]},
            max_files=1,
            timeout=120,
        ).send()
        return

    # Check for identity questions first, regardless of PDF content
    identity_questions = [
        "what is your name", "who are you", "who created you", "what do you do",
        "what can you help me with", "what are you", "who made you", "what's your name",
        "what are your capabilities", "what's your purpose", "what is your purpose",
        "what are you for", "what can you do"
    ]
    
    if any(q in message.content.lower() for q in identity_questions):
        identity_response = """I am Yusra's Assistant, created by Yusra Saleem. I specialize in analyzing PDF documents.

My main capabilities include:
- Reading and analyzing PDF documents
- Answering questions about document content
- Extracting key information from documents
- Helping users understand complex documents

I'm here to help you better understand any PDF documents you share with me. Feel free to upload a PDF and ask me questions about it."""
        await cl.Message(content=identity_response).send()
        return

    # If PDF content already loaded, treat incoming messages as queries
    if pdf_content:
        await process_query(message.content)
        return

    # Otherwise, prompt for file upload
    try:
        files = await cl.AskFileMessage(
            content="Please upload a PDF file to analyze!",
            accept={"application/pdf": [".pdf"]},
            max_files=1,
            timeout=120,
        ).send()

        if not files:
            await cl.Message(content="No file uploaded. Please try again.").send()
            return

        pdf_file = files[0]
        # The uploaded file is already saved temporarily, we can use its path directly
        pdf_text = extract_text_from_pdf(pdf_file.path)

        if pdf_text:
            cl.user_session.set("pdf_content", pdf_text)
            await cl.Message(content=f"PDF '{pdf_file.name}' processed successfully! Ask me questions about the document.").send()
        else:
            await cl.Message(content="Error: Could not extract text from the PDF. Please upload a valid PDF file.").send()

        # No need to remove the file as Chainlit handles cleanup automatically

    except Exception as e:
        print(f"Error during file processing: {e}")
        await cl.Message(content=f"An error occurred while processing the file: {e}").send()


async def process_query(query: str):
    """
    Handle user queries based on the PDF content.
    """
    thinking_msg = cl.Message(content="Thinking...")
    await thinking_msg.send()

    pdf_content = cl.user_session.get("pdf_content")
    if not pdf_content:
        thinking_msg.content = "Error: No PDF content available. Please upload a PDF first."
        await thinking_msg.update()
        return

    history = cl.user_session.get("chat_history") or []

    # Handle request for new PDF analysis
    if any(phrase in query.lower() for phrase in ["analyze another pdf", "upload another pdf", "new pdf", "different pdf", "another document"]):
        upload_msg = "Sure! I can help you analyze another PDF. Please upload the new PDF file."
        thinking_msg.content = upload_msg
        await thinking_msg.update()
        cl.user_session.set("pdf_content", "")  # Clear current PDF content
        await cl.AskFileMessage(
            content="Please upload a PDF file to analyze!",
            accept={"application/pdf": [".pdf"]},
            max_files=1,
            timeout=120,
        ).send()
        return

    # Normal document query handling
    prompt = f"""You are Yusra's Assistant created by Yusra Saleem. Use the following PDF content to answer the user's question.
I want you to analyze the PDF content carefully and provide accurate, helpful responses.

PDF Content:
{pdf_content}

User Question: {query}"""
    history.append({"role": "user", "content": prompt})

    try:
        # Assuming completion() is synchronous; if async, add await
        response = completion(
            model="gemini/gemini-2.0-flash",
            api_key=gemini_api_key,
            messages=history,
        )
        response_content = response.choices[0].message.content

        thinking_msg.content = response_content
        await thinking_msg.update()

        history.append({"role": "assistant", "content": response_content})
        cl.user_session.set("chat_history", history)

        print(f"User: {query}")
        print(f"Assistant: {response_content}")

    except Exception as e:
        thinking_msg.content = f"Error: {str(e)}"
        await thinking_msg.update()
        print(f"Error: {str(e)}")


@cl.on_chat_end
async def on_chat_end():
    """
    Save chat history on chat end.
    """
    history = cl.user_session.get("chat_history") or []
    with open("chat_history.json", "w") as f:
        json.dump(history, f, indent=2)
    print("Chat history saved.")

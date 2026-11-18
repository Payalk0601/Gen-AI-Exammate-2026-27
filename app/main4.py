import os
from datetime import datetime
from google import genai
from google.genai import types

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(api_version="v1beta")
)


# 1. Python Tools

def calculator(a: float, b: float, operation: str):

    if operation == "add":
        return a + b

    elif operation == "subtract":
        return a - b

    elif operation == "multiply":
        return a * b

    elif operation == "divide":
        return a / b


def get_current_time():
    return datetime.now().strftime("%d-%m-%Y %H:%M:%S")


# 2. Tool Registry

tool_registry = {
    "calculator": calculator,
    "get_current_time": get_current_time
}


# 3. Tool Declarations

tools = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="calculator",
                description="Perform mathematical calculations",
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "a": {"type": "NUMBER"},
                        "b": {"type": "NUMBER"},
                        "operation": {
                            "type": "STRING",
                            "enum": ["add", "subtract", "multiply", "divide"]
                        }
                    },
                    "required": ["a", "b", "operation"]
                }
            ),

            types.FunctionDeclaration(
                name="get_current_time",
                description="Get current date and time",
                parameters={
                    "type": "OBJECT",
                    "properties": {}
                }
            )
        ]
    )
]


# 4. Agent Loop

def agent_loop():

    while True:

        user_input = input("\nYou: ")

        if user_input.lower() == "exit":
            break

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=user_input)
                ]
            )
        ]

        while True:

            # THINK
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=types.GenerateContentConfig(
                    tools=tools,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True
                    )
                )
            )


            function_calls = response.function_calls

            # FINAL ANSWER
            if not function_calls:
                print("\nAgent:", response.text)
                break

            # Store Gemini's function call
            contents.append(response.candidates[0].content)

            # ACT
            function_responses = []

            for call in function_calls:

                tool_name = call.name
                arguments = dict(call.args)

                function = tool_registry[tool_name]

                result = function(**arguments)

                print("Tool:", tool_name)
                print("Result:", result)

                # OBSERVE
                function_responses.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": result}
                    )
                )

            # Send tool results back to Gemini
            contents.append(
                types.Content(
                    role="tool",
                    parts=function_responses
                )
            )


agent_loop()
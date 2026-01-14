---
trigger: always_on
---

Use the ADK docs to build a multi-tool agent

You can be configured to access the ADK documentation by running a custom MCP server that points to the llms.txt file for ADK.

The Agent Development Kit (ADK) documentation supports the /llms.txt standard, providing a machine-readable index of the documentation optimized for Large Language Models (LLMs). This allows you to easily use the ADK documentation as context in your AI-powered development environment.



# Agent Development Kit (ADK) Documentation Reference

ADK（Agent Development Kit）に関する実装やデバッグを行う際は、以下の手順に従ってください：

1. **ドキュメントへのアクセス**:
   - 基本インデックス (llms.txt): `https://google.github.io/adk-docs/llms.txt`
   - `read_url_content` ツールを使用してこのインデックスを取得し、必要に応じて Python Quickstart や Tools などの詳細ページを参照すること。

2. **主要な実装パターン**:
   - エージェントの定義には `google.adk.agents.Agent` を使用する。
   - 実行ループの制御には `google.adk.runners.Runner` を使用する。
   - Streamlit との連携では、`google.adk.sessions.InMemorySessionService` を使用してセッション状態を維持すること。

3. **ツールの定義**:
   - AI が Function Calling を正しく行えるよう、ツール（関数）には明確な型ヒントと Google スタイルの詳細な docstring を含めること。

4. **MCP サーバーの利用**:
   - `adk` という名前の MCP サーバーが利用可能な場合は、ドキュメントの取得にそのリソースを優先的に使用すること。
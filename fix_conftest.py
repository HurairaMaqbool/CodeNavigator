import re
import os

with open('tests/conftest.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove the old fixture if it exists
content = re.sub(r'import pytest\nfrom unittest\.mock import MagicMock, patch\n\n@pytest\.fixture\(autouse=True\).*?yield mock_client\n', '', content, flags=re.DOTALL)

fixture = '''
import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture(autouse=True)
def mock_chroma_for_non_integration_tests(request):
    integration_tests = ['test_retrieval_6a.py', 'test_retrieval_6b.py', 'test_module_6a.py', 'test_module_6b.py']
    if any(request.node.fspath.basename == name for name in integration_tests):
        yield
        return
        
    with patch('app.agent.semantic_cache.chromadb.PersistentClient', MagicMock()) as mock_client:
        mock_col = MagicMock()
        mock_col.count.return_value = 0
        mock_col.query.return_value = {'ids': [['stale_id']], 'distances': [[0.0]], 'metadatas': [[{'answer_json': '{"answer": "Stale", "cache_hit": True, "confidence": "high", "gated": False}', 'repo_commit_hash': 'commit123'}]]}
        mock_col.metadata = {"embedding_model_id": "all-MiniLM-L6-v2"}
        mock_client.return_value.get_collection.return_value = mock_col
        mock_client.return_value.create_collection.return_value = mock_col
        yield mock_client
'''

with open('tests/conftest.py', 'w', encoding='utf-8') as f:
    f.write(content + '\n' + fixture)

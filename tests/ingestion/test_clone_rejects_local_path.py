import pytest
from app.ingestion.clone import clone_repo, InvalidURLError

@pytest.mark.parametrize("local_path", [
    "C:/some/local/path",
    "/tmp/localrepo",
    "../relative/path",
])
def test_clone_rejects_local_path(local_path):
    """Ensure clone_repo raises InvalidURLError for local filesystem paths."""
    with pytest.raises(InvalidURLError):
        clone_repo(local_path)

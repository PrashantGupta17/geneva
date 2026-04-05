import os
from dbos import DBOS

@DBOS.workflow()
def my_workflow():
    return 1

def test_run():
    if os.environ.get("DBOS_DISABLE") == "1":
        assert my_workflow.__wrapped__() == 1
    else:
        DBOS.launch()
        assert my_workflow() == 1

if __name__ == "__main__":
    test_run()

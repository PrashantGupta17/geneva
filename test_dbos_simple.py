from dbos import DBOS

@DBOS.workflow()
def test():
    return 1

if __name__ == "__main__":
    DBOS.launch()
    print(test())

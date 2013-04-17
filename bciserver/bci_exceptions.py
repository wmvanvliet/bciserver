class EngineException(Exception):
    def __init__(self, code, msg):
        self.code = code
        self.msg = msg

    def __str__(self):
        return '%d: %s' (self.code, self.msg)

class BCIProtocolException(Exception):
    def __init__(self, code, msg):
        self.code = code
        self.msg = msg

    def __str__(self):
        return '%d: %s' % (self.code, self.msg)

class ClassifierException(Exception):
    pass

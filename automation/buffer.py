class Buffer(list):
    r"""
    Documentation here
    """

    def __init__(self, size:int=10, roll:str='forward'):
        r"""
        Documentation here
        """
        self._roll_type_allowed = ['forward', 'backward']
        self._size = size
        self.roll = roll

    @property
    def size(self):
        r"""
        Documentation here
        """
        return self._size

    @size.setter
    def size(self, value:int):
        r"""
        Documentation here
        """
        if not isinstance(value, int):

            raise TypeError("Only integers are allowed")

        if value <= 1:

            raise ValueError(f"{value} must be greater than one (1)")
        

        self.__init__(value, roll=self.roll)

    def last(self):
        r"""
        Returns last registered value of the buffer
        """
        if self:

            if self.roll == 'forward':

                return self[-1]
            
            return self[0]
    
    def current(self):
        r"""
        Returns lastest registered value of the buffer
        """  
        if self: 

            if self.roll == 'forward':
                
                return self[0]
            
            return self[-1]
        
    def previous_current(self):
        r"""
        Returns lastest registered value of the buffer
        """  
        if self: 

            if self.roll == 'forward':
                
                return self[1]
            
            return self[-2]
    
    def apply_each(self, fn, start:int=None, stop:int=None):
        r"""
        Applies a function to each item of a subset of the buffer, and returns the modified buffer
        """
        foo = self

        if start <= stop:

            if start:
                foo = foo[start:]

            if stop:
                foo = foo[:stop]

        if hasattr(fn, '__call__'):
            foo = map(lambda x: fn(x), foo)

        return foo
    
    def apply(self, fn, start:int=None, stop:int=None):
        r"""
        Applies a function to a subset of the buffer, and returns the result
        """

        foo = self

        if start <= stop:

            if start:
                foo = foo[start:]

            if stop:
                foo = foo[:stop]

        if hasattr(fn, '__call__'):
            foo = fn(foo)

        return foo    

    @property
    def roll(self):
        r"""
        Documentation here
        """
        return self.roll_type

    @roll.setter
    def roll(self, value:str):
        r"""
        Documentation here
        """
        if not isinstance(value, str):

            raise TypeError("Only strings are allowed")

        if value not in self._roll_type_allowed:
            
            raise ValueError(f"{value} is not allowed, you can only use: {self._roll_type_allowed}")

        self.roll_type = value

    def __call__(self, value):
        r"""
        Documentation here
        """
        if self.roll.lower()=='forward':
            
            _len = len(self)
            
            if _len > self.size:
                
                if _len == self.size:
                    
                    self.pop()
                
                else:

                    for _ in range(_len - self.size):

                        self.pop()

            super(Buffer, self).insert(0, value)

        else:

            _len = len(self)
            
            if _len > self.size:
                
                if _len == self.size:
                    
                    self.pop(0)
                
                else:

                    for _ in range(_len - self.size):

                        self.pop(0)
                
            super(Buffer, self).append(value)

        return self
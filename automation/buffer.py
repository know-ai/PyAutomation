class Buffer(list):
    r"""
    A circular buffer implementation that extends the built-in `list`.

    It stores a fixed number of items (`size`). When the buffer is full, new items overwrite
    existing ones based on the `roll` strategy ('forward' or 'backward').

    **Usage:**

    ```python
    buf = Buffer(size=3)
    buf(1)
    buf(2)
    buf(3)
    buf(4) # Overwrites 1
    print(buf) # [4, 3, 2] (if roll='forward' insertion at 0)
    ```
    """

    def __init__(self, size:int=10, roll:str='forward'):
        r"""
        Initializes the Buffer.

        **Parameters:**

        * **size** (int): Maximum number of elements.
        * **roll** (str): Direction of insertion/overwrite.
            * `'forward'`: Inserts at index 0 (LIFO-like display).
            * `'backward'`: Appends to end (FIFO-like).
        """
        self._roll_type_allowed = ['forward', 'backward']
        self._size = size
        self.roll = roll

    @property
    def size(self):
        r"""
        Gets the maximum size of the buffer.
        """
        return self._size

    @size.setter
    def size(self, value:int):
        r"""
        Sets the buffer size. Resets the buffer if changed.

        **Parameters:**

        * **value** (int): New size (must be > 1).
        """
        if not isinstance(value, int):

            raise TypeError("Only integers are allowed")

        if value <= 1:

            raise ValueError(f"{value} must be greater than one (1)")
        

        self.__init__(value, roll=self.roll)

    def last(self):
        r"""
        Returns the oldest value in the buffer.

        **Returns:**

        * The last item based on roll direction.
        """
        if self:
            if self.roll == 'forward':

                return self[-1]
            
            return self[0]
    
    def current(self):
        r"""
        Returns the most recently added value.

        **Returns:**

        * The newest item.
        """  
        if self:
            if self.roll == 'forward':
                
                return self[0]
            
            return self[-1]
        
    def previous_current(self):
        r"""
        Returns the second most recent value.

        **Returns:**

        * The item before current.
        """
        if self:
            if self.roll == 'forward':
                
                return self[1]
            
            return self[-2]

    @property
    def roll(self):
        r"""
        Gets the roll type ('forward' or 'backward').
        """
        return self.roll_type

    @roll.setter
    def roll(self, value:str):
        r"""
        Sets the roll type.

        **Parameters:**

        * **value** (str): 'forward' or 'backward'.
        """
        if not isinstance(value, str):

            raise TypeError("Only strings are allowed")

        if value not in self._roll_type_allowed:
            
            raise ValueError(f"{value} is not allowed, you can only use: {self._roll_type_allowed}")

        self.roll_type = value

    def __call__(self, value):
        r"""
        Adds a new value to the buffer.

        If the buffer is full, it removes the oldest item to make space.

        **Parameters:**

        * **value**: The item to add.

        **Returns:**

        * **Buffer**: Self (for chaining).
        """
        if self.roll.lower()=='forward':
            
            _len = len(self)
            
            if _len >= self.size:
                
                if _len == self.size:
                    
                    self.pop()
                
                else:

                    for _ in range(_len - self.size):

                        self.pop()

            super(Buffer, self).insert(0, value)

        else:

            _len = len(self)
            
            if _len >= self.size:
                
                if _len == self.size:
                    
                    self.pop(0)
                
                else:

                    for _ in range(_len - self.size):

                        self.pop(0)
                
            super(Buffer, self).append(value)

        return self

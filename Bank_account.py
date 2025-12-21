class BankAccount:
    def __init__(self, owner , balance):
        self.owner = owner
        self. __balance = balance
        #private attribute

    def deposit (self, amount):
        if amount > 0 :
           self. __balance += amount
           print(f"Added{amount}. New balance:{self.__balance}")
        else:
            print("Deposit amount must be positive!")
    def withdraw (self, amount):
        if 0 < amount <= self.__balance:
            self.__balance -= amount
            print(f"Withdrew {amount}. New balance: {self.__balance}")
        else:
            print("Insufficient funds or invalid withdrawal amount!")
            
            
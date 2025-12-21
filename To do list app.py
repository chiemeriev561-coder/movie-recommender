# Create an empty list to store our to-do items
to_do_list = []

def save_list():
    try:
        with open("todo.txt", "w", encoding="utf-8") as file:
            for task in to_do_list:
                file.write(task + "\n")
        print("To-do list saved successfully!")
        return True
    except Exception as e:
        print(f"Error saving file: {e}")
        return False
def load_list():
    global to_do_list
    try:
        with open("todo.txt", "r", encoding="utf-8") as file:
            to_do_list = [line.strip() for line in file if line.strip()]
        print("To-do list loaded successfully!")
    except FileNotFoundError:
        print("No saved to-do list found. Starting with an empty list.")
    except Exception as e:
        print(f"Error loading file: {e}") 
# Load existing to-do list from file at the start
load_list()               
             
# This loop will keep the program running until the user quits
while True:
    print("\n--- To-Do List Menu ---")
    print("1. Add a new task")
    print("2. View all tasks")
    print("3. Delete a task")
    print("4. Quit")
    
    choice = input("Enter your choice (1-4): ")
    
    # --- Option 1: Add a new task ---
    if choice == "1":
        task = input("Enter the new task: ").strip()
        if task:
            to_do_list.append(task)
            print(f"Task '{task}' added!")
        else:
            print("No task entered. Nothing added.")
    
    # --- Option 2: View all tasks ---
    elif choice == "2":
        print("\nYour To-Do List:")
        if not to_do_list:
            print("Your to-do list is empty!")
        else:
            for i, task in enumerate(to_do_list, start=1):
                print(f"{i}. {task}")
                
    # --- Option 3: Delete a task ---
    elif choice == "3":
        if not to_do_list:
            print("No tasks to delete.")
            continue
        try:
            task_number = int(input("Enter the number of the task to delete: ").strip())
            if 1 <= task_number <= len(to_do_list):
                removed_task = to_do_list.pop(task_number - 1)
                print(f"Task '{removed_task}' deleted successfully.")
            else:
                print("Invalid task number.")
        except ValueError:
            print("Invalid input. Please enter a number.")
    
    # --- Option 4: Quit the program ---
    elif choice == "4":
        if save_list():
            print("Save successful! Goodbye!")
        else:
            print("Save failed! Goodbye!")
        break
    else:
         print("Invalid choice. Please enter 1-4")
             

                

            
    
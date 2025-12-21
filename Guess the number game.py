import random
import time
import os
from statistics import mean
from statistics import mean

# Offline-only: keep leaderboard and stats in-memory (no file I/O)
leaderboard = []
stats = {"games_played": 0, "wins": 0, "losses": 0, "guesses": [], "streak": 0, "best_streak": 0, "achievements": []}


DIFFICULTIES = {
     "easy": {"min": 1, "max": 50, "max_guesses": 10},
     "normal": {"min": 1, "max": 100, "max_guesses": 8},
     "hard": {"min": 1, "max": 500, "max_guesses": 7}
}


def earn_achievement(name):
     if name not in stats.get("achievements", []):
          stats.setdefault("achievements", []).append(name)
          print(f"Achievement unlocked: {name}!")


def record_game(entry):
     leaderboard.append(entry)
     leaderboard.sort(key=lambda x: (x.get("guesses", 999), x.get("time_seconds", 9999)))



def update_stats(win, guesses, time_seconds):
     stats["games_played"] = stats.get("games_played", 0) + 1
     if win:
          stats["wins"] = stats.get("wins", 0) + 1
          stats["streak"] = stats.get("streak", 0) + 1
          stats["best_streak"] = max(stats.get("best_streak", 0), stats.get("streak", 0))
     else:
          stats["losses"] = stats.get("losses", 0) + 1
          stats["streak"] = 0
     stats.setdefault("guesses", []).append(guesses)



def show_leaderboard(n=10):
     if not leaderboard:
          print("No leaderboard entries yet.")
          return
     print("\nLeaderboard (best by fewest guesses):")
     for i, e in enumerate(leaderboard[:n], 1):
          print(f"{i}. {e.get('name','Anonymous')} — guesses: {e.get('guesses')} time: {e.get('time_seconds'):.1f}s mode: {e.get('mode')}")


def show_stats():
     print("\nPlayer stats:")
     print(f"Games played: {stats.get('games_played',0)} Wins: {stats.get('wins',0)} Losses: {stats.get('losses',0)}")
     if stats.get("guesses"):
          print(f"Avg guesses per game: {mean(stats['guesses']):.2f} Best streak: {stats.get('best_streak',0)}")
     if stats.get("achievements"):
          print("Achievements:", ", ".join(stats['achievements']))


def pick_difficulty(adaptive=None):
     if adaptive is None:
          adaptive = True
     print("Choose difficulty:")
     print("1) Easy (1-50)")
     print("2) Normal (1-100)")
     print("3) Hard (1-500)")
     print("4) Progressive (levels increase range)")
     choice = input("Select 1-4 (enter for Normal): ").strip()
     if choice == '1':
          return 'easy'
     if choice == '3':
          return 'hard'
     if choice == '4':
          return 'progressive'
     return 'normal'


def hint_options(secret, low, high):
     # returns a dict of available hints
     hints = {}
     hints['parity'] = 'even' if secret % 2 == 0 else 'odd'
     hints['divisible_by_3'] = (secret % 3 == 0)
     # proximity hint
     span = max(1, (high - low) // 10)
     hints['within'] = span
     return hints


def play_single(player_name="Player", mode='normal', timed=False, progressive=False):
     # Setup difficulty range
     if progressive:
          level = 1
     else:
          level = None

     current_diff = mode
     adaptive = True
     while True:
          if progressive:
               # increase range each level
               rng_min = 1
               rng_max = 10 * (2 ** (level - 1))
               max_guesses = max(3, 8 - (level // 2))
               print(f"\nProgressive Level {level}: guess between {rng_min} and {rng_max} (max guesses {max_guesses})")
          else:
               d = DIFFICULTIES.get(current_diff, DIFFICULTIES['normal'])
               rng_min, rng_max, max_guesses = d['min'], d['max'], d['max_guesses']

          secret = random.randint(rng_min, rng_max)
          guesses = 0
          start = time.time() if timed else None
          used_hints = 0
          powerups = {'reveal_parity': True, 'halve_range': True}
          low, high = rng_min, rng_max

          print("Game started. Type 'hint' to use a hint (costs 1 guess), 'power' for power-ups, or 'q' to quit.")
          while guesses < max_guesses:
               remaining = max_guesses - guesses
               prompt = f"Guess a number between {low} and {high} (remaining guesses {remaining}): "
               val = input(prompt).strip().lower()
               if val == 'q':
                    print('Quitting current game.')
                    update_stats(False, guesses, 0)
                    return
               if val == 'hint':
                    used_hints += 1
                    guesses += 1
                    h = hint_options(secret, low, high)
                    print(f"Hint: The number is {h['parity']}. Divisible by 3: {h['divisible_by_3']}. It's within ±{h['within']} of its neighborhood.")
                    continue
               if val == 'power':
                    print("Available power-ups:")
                    if powerups.get('reveal_parity'):
                         print("1) Reveal parity (free)")
                    if powerups.get('halve_range'):
                         print("2) Halve the searching range (consumes power-up)")
                    p = input("Choose power-up (or enter to cancel): ").strip()
                    if p == '1' and powerups.get('reveal_parity'):
                         powerups['reveal_parity'] = False
                         print('Power-up: The number is', 'even' if secret % 2 == 0 else 'odd')
                    elif p == '2' and powerups.get('halve_range'):
                         powerups['halve_range'] = False
                         mid = (low + high) // 2
                         if secret <= mid:
                              high = mid
                         else:
                              low = mid + 1
                         print(f'Power-up used. New range {low} to {high}.')
                    else:
                         print('No power-up used.')
                    continue

               try:
                    guess = int(val)
               except ValueError:
                    print('Invalid input. Type a number, "hint", "power", or "q".')
                    continue

               guesses += 1
               if guess < secret:
                    print('Too low!')
                    low = max(low, guess + 1)
               elif guess > secret:
                    print('Too high!')
                    high = min(high, guess - 1)
               else:
                    elapsed = (time.time() - start) if timed and start else 0.0
                    print(f'Congratulations {player_name}! You guessed the number in {guesses} guesses{(f" and {elapsed:.1f}s" if timed else "")}')
                    update_stats(True, guesses, elapsed)
                    record_game({"name": player_name, "guesses": guesses, "time_seconds": elapsed, "mode": 'progressive' if progressive else current_diff})
                    if guesses == 1:
                         earn_achievement('Lucky 1st Guess')
                    if stats.get('streak', 0) >= 10:
                         earn_achievement('10-win Streak')
                    # adaptive difficulty: if won easily, increase difficulty
                    if not progressive and adaptive:
                         if guesses <= max(3, max_guesses // 3):
                              if current_diff == 'easy':
                                   current_diff = 'normal'
                              elif current_diff == 'normal':
                                   current_diff = 'hard'
                              print(f'Adaptive: increasing difficulty to {current_diff}.')
                    if progressive:
                         level += 1
                         continue_game = input('Advance to next level? (enter to continue, q to quit): ').strip().lower()
                         if continue_game == 'q':
                              return
                         else:
                              continue
                    return

          # ran out of guesses
          print(f'Sorry, you ran out of guesses. The number was {secret}.')
          update_stats(False, guesses, 0)
          earn_achievement('First Loss')
          return


def hotseat_mode():
     p1 = input('Player 1 name: ').strip() or 'Player1'
     p2 = input('Player 2 name: ').strip() or 'Player2'
     players = [p1, p2]
     current = 0
     rounds = 1
     while True:
          print(f"\nRound {rounds}: {players[current]}'s turn")
          play_single(player_name=players[current], mode='normal')
          current = 1 - current
          rounds += 1
          cont = input('Continue hotseat? (enter to continue, q to stop): ').strip().lower()
          if cont == 'q':
               break


def reverse_mode():
     print('Reverse mode: the computer will try to guess your number.')
     choice = input('Do you want to (1) enter your number now (hidden) or (2) let the computer ask you interactively? (1/2): ').strip()
     if choice == '1':
          while True:
               try:
                    secret = int(input('Enter the secret number for the computer to guess: ').strip())
                    break
               except ValueError:
                    print('Enter a valid integer.')
          low, high = 1, max(100, secret * 2)
          guesses = 0
          start = time.time()
          while True:
               guess = (low + high) // 2
               guesses += 1
               print(f'Computer guesses {guess}')
               if guess == secret:
                    elapsed = time.time() - start
                    print(f'Computer found the number in {guesses} guesses ({elapsed:.1f}s)')
                    record_game({"name": 'Computer', "guesses": guesses, "time_seconds": elapsed, "mode": 'reverse'})
                    return
               if guess < secret:
                    print('Too low (computer).')
                    low = guess + 1
               else:
                    print('Too high (computer).')
                    high = guess - 1

     else:
          print('Think of a number and tell the computer if its guess is higher/lower/correct.')
          low, high = 1, 1000
          guesses = 0
          start = time.time()
          while True:
               guess = (low + high) // 2
               guesses += 1
               resp = input(f'Is {guess} (h)igher, (l)ower, or (c)orrect? ').strip().lower()
               if resp in ('c', 'correct'):
                    elapsed = time.time() - start
                    print(f'Computer guessed correctly in {guesses} guesses ({elapsed:.1f}s)')
                    record_game({"name": 'Computer', "guesses": guesses, "time_seconds": elapsed, "mode": 'reverse'})
                    return
               if resp in ('h', 'higher'):
                    low = guess + 1
               elif resp in ('l', 'lower'):
                    high = guess - 1
               else:
                    print('Please reply h/l/c.')


def main_menu():
     print('Welcome to the enhanced Guess The Number game!')
     while True:
          print('\nMain menu:')
          print('1) Play single-player')
          print('2) Play progressive mode')
          print('3) Hotseat multiplayer')
          print('4) Reverse mode (computer guesses)')
          print('5) View leaderboard')
          print('6) View stats & achievements')
          print('7) Reset stats/leaderboard')
          print('q) Quit')
          choice = input('Choose an option: ').strip().lower()
          if choice == '1':
               name = input('Enter your name: ').strip() or 'Player'
               diff = pick_difficulty()
               timed = input('Timed mode? (y/N): ').strip().lower() == 'y'
               play_single(player_name=name, mode=diff, timed=timed)
          elif choice == '2':
               name = input('Enter your name: ').strip() or 'Player'
               play_single(player_name=name, progressive=True)
          elif choice == '3':
               hotseat_mode()
          elif choice == '4':
               reverse_mode()
          elif choice == '5':
               show_leaderboard()
          elif choice == '6':
               show_stats()
          elif choice == '7':
               confirm = input('Type YES to reset stats and leaderboard: ').strip()
               if confirm == 'YES':
                       leaderboard.clear()
                       stats.clear()
                       stats.update({"games_played": 0, "wins": 0, "losses": 0, "guesses": [], "streak": 0, "best_streak": 0, "achievements": []})
                       print('In-memory reset done.')
          elif choice == 'q':
               print('Goodbye!')
               break
          else:
               print('Invalid choice.')


if __name__ == '__main__':
     main_menu()

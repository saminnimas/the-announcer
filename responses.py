from random import choice, randint

# 3
def get_response(user_input: str) -> str:
    # raise NotImplementedError('Code is Under construction')
    lowered: str = user_input.lower()

    if lowered == '':
        return 'Well, you\'re awfully silent...'
    elif 'hello' in lowered:
        return 'Hello There!'
    elif 'how are you' in lowered:
        return 'Good. What about you?'
    elif 'fine' in lowered:
        return 'Good'
    elif 'roll dice' in lowered:
        return f'You rolled: {randint(1, 6)}'
    else:
        return choice(['This is not in my vocabulary',
                       'Come again',
                       'I do not understand',
                       f'What\'s {user_input}?'])

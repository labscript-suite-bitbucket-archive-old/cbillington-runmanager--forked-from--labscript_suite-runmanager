import string
import tokenize
import io
import ast
from decimal import Context, Decimal, setcontext, getcontext

decimal_context = Context()

digits_by_base = {2: '01', 8: string.octdigits, 10: string.digits, 16: string.hexdigits}


def is_digit(src, index):
    """Return whether the character at the given index is a digit of a syntactically
    valid Python numerical literal, or is a bool (True or False), which we are kind of
    treating like integers modulo 2. Also returns the range of the digit in the src,
    which of course is just index:index+1 for a digit, but i the extent of the bool
    literal if it's a bool"""
    start, end, base = getnum(src, index)
    if base is not None and src[index] in digits_by_base[base]:
        return True, index, index+1
    elif start is not None:
        return True, start, end
    return False, None, None


def getnum(src, index):
    """If there is a digit of a numerical literal at the given index of the single-line
    src, return the start and end index of the literal, and its base. If a negative sign
    immediately precedes the literal, it will be included. The significand and exponent
    of floats in exponential notation will be treated as separate literals, and any
    positive sign present before the exponent will be included in the result (positive
    signs before other literals will not be included). If there is a boolean literal
    (True or False) at index, then return it, but with None for the base."""
    assert '\n' not in src
    assert index < len(src)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            start = tok.start[1]
            end = tok.end[1]
            if start <= index < end:
                if tok.type == tokenize.NUMBER:
                    expr = tok.string
                    if '0x' in expr.lower():
                        base = 16
                    elif '0o' in expr.lower():
                        base = 8
                    elif '0b' in expr.lower():
                        base = 2
                    else:
                        base = 10
                        if 'e' in expr.lower():
                            pos = expr.lower().find('e')
                            if pos < index:
                                start += pos + 1
                            else:
                                end = start + pos
                    # Must be an actual digit at index, not a decimal point, underscore, or
                    # the 0 in the prefix of hex/binary/octal literals
                    if (
                        src[index] not in digits_by_base[base]
                        or base != 10
                        and index == start
                    ):
                        return None, None, None
                    if start:
                        if src[start - 1] == '-':
                            start -= 1
                    return start, end, base
                elif tok.type == tokenize.NAME and tok.string in ('True', 'False'):
                    return start, end, None
    except tokenize.TokenError:
        # End of incomplete expression. We are done.
        pass
    return None, None, None


def increment_at_index(src, index, increment):
    """Given a single-line source and an index, if there is a digit of a numeric literal
    at that index, increment (if increment=+1) or decrement (if increment=-1) it in that
    digit, otherwise preserving the source. If there is a boolean literal (True or
    False), invert it. Return the new source and the offset for how much the cursor
    should move as a result of the transformation."""
    assert increment in (+1, -1)
    if not src:
        return src, 0
    start, end, base = getnum(src, index)
    if start is None:
        return src, 0

    expr = src[start:end]

    if base == 10:
        decimalpoint = start + expr.find('.')
        if decimalpoint == start - 1:
            decimalpoint = end
        if decimalpoint > index:
            exponent = decimalpoint - index - expr[index:decimalpoint].count('_') - 1
        else:
            exponent = decimalpoint - index + expr[decimalpoint:index].count('_')
        if len(expr) > decimal_context.prec:
            decimal_context.prec = len(expr) + 5

        orig_context = getcontext()
        setcontext(decimal_context)
        value = Decimal(expr) + increment * Decimal(10) ** exponent
        result = str(value)
        setcontext(orig_context)

        # Leading zeros are allowed in float exponents. If it has leading zeros, let's
        # pad our result out to the same length:
        digits_only = expr.lstrip('+-').replace('_', '')
        if digits_only.startswith('0'):
            result = result.lstrip('+-').zfill(len(digits_only))
            if value < 0:
                result = '-' + result

        # Preserve redundant + signs in floating point exponents
        if expr.startswith('+') and not result.startswith('-'):
            result = '+' + result

    elif expr == 'True':
        result = 'False'
    elif expr == 'False':
        result = 'True'
    else:
        value = ast.literal_eval(expr)
        exponent = end - index - expr[index:].count('_') - 1
        value += increment * base ** exponent
        if base == 2:
            result = expr[:2] + bin(value)[2:]
        elif base == 8:
            result = expr[:2] + oct(value)[2:]
        elif base == 16:
            # If the string has any lower case hex then we will output lower case hex:
            if any(s in string.ascii_lowercase for s in expr[2:]):
                result = expr[:2] + hex(value)[2:].lower()
            else:
                result = expr[:2] + hex(value)[2:].upper()
        else:
            result = str(value)
    
    

    # How much of the resulting expression is actual digits, vs base prefixes and sign?
    prefix = 0
    if result[0] in '+-':
        prefix += 1
    if base in [2, 8, 16]:
        prefix += 2

    # Location of underscores in orig expression, as negative indices (i.e. measured
    # from the end):
    underscores = [i - len(expr) for i, s in enumerate(expr) if s == '_']

    # Re-insert underscores from right-to-left:
    arr = list(result)
    for i in underscores[::-1]:
        if i + len(arr) + 1 > prefix:
            arr.insert(i + 1, '_')

    result = ''.join(arr)

    offset = len(result) - len(expr)
    if index + offset - start < prefix:
        offset = start - index + prefix
    return src[:start] + result + src[end:], offset


if __name__ == '__main__':

    test_cases = [
        ("a", 0, +1, "a", 0),  # Do nothing
        ("1", 0, +1, "2", 0),  # increment
        ("1", 0, -1, "0", 0),  # decrement
        ("9", 0, +1, "10", 1),  # carry up
        ("30", 1, -1, "29", 0),  # carry down
        ("a0", 0, -1, "a0", 0),  # do nothing
        ("0", 0, -1, "-1", 1),  # test sign flip
        ("-1", 1, +1, "0", -1),  # zero should be positive
        ("-10", 1, +1, "0", -1),  # same but with a different digit, and removing zeros.
        ("1_0", 2, +1, "1_1", 0),  # simple with underscore
        ("1.0", 2, +1, "1.1", 0),  # simple with decimal point
        ("1_9", 2, +1, "2_0", 0),  # carry up with underscore
        ("10", 1, -1, "9", -1),  # lop off preceding zero
        ("10000", 0, -1, "0", 0),  # remove these zeros
        ("1.0", 2, -1, "0.9", 0),  # but not this one
        ("1_0", 2, -1, "9", -2),  # but yes this one
        ("a10", 2, -1, "a10", 0),  # Do nothing
        ("0xa", 2, +1, "0xb", 0),  # lower case hex
        ("0xA", 2, +1, "0xB", 0),  # upper case hex
        ("0xfff", 4, +1, "0x1000", 1),  # hex with carrying
        ("0b1011", 2, +1, "0b10011", 1),  # binary
        ("-10", 2, +1, "-9", -1),  # negative increment
        ("-10", 2, -1, "-11", 0),  # negative decrement
        ("1.4e6", 2, -1, "1.3e6", 0),  # float with exponent
        ("1.4e6", 4, -1, "1.4e5", 0),  # float with exponent - decrement exponent
        ("1.4e0", 4, -1, "1.4e-1", 1),  # sign flip in exponent
        ("1.4e-10", 5, +1, "1.4e0", -1),  # sign flip in exponent the other way
        ("0.01", 2, -1, "-0.09", 1),  # sign change with nonzero digits to the right
        ("-0.01", 3, +1, "0.09", -1),  # similar thing the other way around
        ("1e+5", 3, +1, "1e+6", 0),  # Retain the + in the exponent
        ("1E5", 2, +1, "1E6", 0),  # Retain the capital E in the exponent
        ("1E5", 0, +1, "2E5", 0),  # No decimal point
        ("1E+0", 3, -1, "1E-1", 0),  # Replace the + with - when exponent changes sign
        ("1_0E1_0", 2, 1, "1_1E1_0", 0),  # Underscores in both significand and exponent
        ("0Xabcd", 2, +1, "0Xbbcd", 0),  # Retain capitalisation of X in prefix
        ("0xabcd", 0, +1, "0xabcd", 0),  # Don't touch the prefix 0
        ("0xab_cd", 3, +1, "0xac_cd", 0),  # Underscores in hex
        ("-11.0", 1, +1, "-1.0", 0),  # Offset shouldn't move the cursor to a minus sign
        ("0x10100", 2, -1, "0x100", 0,),  # Offset shouldn't move us over the prefix
        ("1 + 1.0", 6, +1, "1 + 1.1", 0), # Preceding text shouldn't matter
        ("1 + 1", 4, +1, "1 + 2", 0), # Preceding text shouldn't matter
        ("1.001", 4, -1, "1.000", 0), # Should not throw away these zeros
        ("1 + True", 4, -1, "1 + False", 1), # bools
        ("1 + False", 8, -1, "1 + True", -1), # bools
        ("-0e2", 1, +1, "1e2", -1), # Correctly compute decimal point with leading -
        ("-1.1e2", 3, +1, "-1.0e2", 0), # Another example of the above
        ("1e00", 3, +1,"1e01", 0), # keep redundant leading zeros in exponents
        ("1e+0_0_1", 7, +1,"1e+0_0_2", 0), # Deal with this monstrosity
        ("1.99_88", 5, +1,"1.99_98", 0) # Underscores after the decimal point
    ]

    print(
        f'{"orig":>10}[{"i"}] {"inc":>2}   '
        + f'→  {"expected":>7} ({"offset":>2}) :'
        + f' {"result":>7} ({"offset":>2})',
    )
    print('-' * 60)
    for orig, index, increment, expected_result, expected_dc in test_cases:
        result, dc = increment_at_index(orig, index, increment)
        if result != expected_result or expected_dc != dc:
            success = '!!FAIL!!'
        else:
            success = 'pass'
        print(
            f'{orig:>10}[{index}] {increment:>2}   '
            + f'→  {expected_result:>7} ({expected_dc:>2}) :'
            + f' {result:>7} ({dc:>2}) {success:>10}',
        )

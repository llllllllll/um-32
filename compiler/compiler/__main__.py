import sys


def main():
    if len(sys.argv) not in (2, 3):
        print(
            f'usage: {sys.argv[0]} SOURCE-FILE [OUT-FILE]',
            file=sys.stderr,
        )
        return -1

    from compiler.compiler import compile

    try:
        out_path = sys.argv[2]
    except IndexError:
        out_path = 'a.um'

    with open(sys.argv[1]) as source_file, open(out_path, 'wb') as out_file:
        out_file.write(compile(source_file.read()))

    return 0


if __name__ == '__main__':
    exit(main())

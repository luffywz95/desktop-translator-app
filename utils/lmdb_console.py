import sys
import lmdb
import json


def view_all_keys():
    try:
        # Path to your storage folder
        env = lmdb.open("./storage", readonly=True)

        with env.begin() as txn:
            cursor = txn.cursor()
            for key, value in cursor:
                print(f"KEY: {key.decode('utf-8')}")
                # Attempt to decode JSON, otherwise print raw bytes
                try:
                    data = json.loads(value.decode("utf-8"))
                    print(f"VALUE: {json.dumps(data, indent=4)}")
                except Exception as e:
                    print(f"VALUE: {value}")
                    print(f"Error: {e}")
                print("-" * 30)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        env.close()


def view_key(key):
    try:
        env = lmdb.open("./storage", readonly=True)
        with env.begin() as txn:
            value = txn.get(key.encode("utf-8"))
            if value is None:
                print(f"Key '{key}' not found")
                return
            print(f"VALUE: {json.dumps(json.loads(value.decode('utf-8')), indent=4)}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        env.close()


def delete_key(key):
    try:
        env = lmdb.open("./storage", readonly=False)

        with env.begin(write=True) as txn:
            key_to_delete = key.encode("utf-8")

            # txn.delete returns True if the item was found and deleted
            result = txn.delete(key_to_delete)

            if result:
                print("Key deleted successfully.")
            else:
                print("Key not found.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        env.close()


if __name__ == "__main__":
    print("LMDB Console")
    print("--------------------------------")

    # Read user input
    user_input = input("Enter a command: ")

    args = user_input.split()
    if len(args) == 0:
        print("Usage: python lmdb_console.py <command> [<key>]")
        print("Commands: --view-all, --view, --delete")
        sys.exit(1)

    command = args[0]
    match command:
        case "--view-all" | "--va":
            view_all_keys()
        case "--view" | "--v":
            if len(args) == 1:
                print("Usage: python lmdb_console.py --view <key>")
                sys.exit(1)
            view_key(args[1])
        case "--delete" | "--d":
            if len(args) == 1:
                print("Usage: python lmdb_console.py --delete <key>")
                sys.exit(1)
            delete_key(args[1])
        case _:
            print("Usage: python lmdb_console.py --view-all")
            print("Usage: python lmdb_console.py --view <key>")
            print("Usage: python lmdb_console.py --delete <key>")
            sys.exit(1)

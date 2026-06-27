with open('old_main_utf8.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

restored = ''.join(lines[1084:1493])

with open('main.py', 'r', encoding='utf-8') as f:
    main_content = f.read()

# find STEP 18: API ROUTES
new_main = main_content.replace('STEP 18: API ROUTES', 'RESTORED FUNCTIONS\\n' + restored + '\\n# STEP 18: API ROUTES')

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(new_main)

print('Restored successfully')

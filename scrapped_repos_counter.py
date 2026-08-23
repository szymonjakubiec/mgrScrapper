sum_saved = 0
sum_bad = 0
sum_no_content = 0

with open('repos_results_log.txt', 'r', encoding='utf-8') as file:
    for line in file:
        if line.startswith('Saved:'):
            sum_saved += int(line.split(':')[1].split()[0])

        elif line.startswith('Discarded (Bad):'):
            sum_bad += int(line.split(':')[1].split()[0])

        elif line.startswith('Discarded (No Content):'):
            sum_no_content += int(line.split(':')[1].split()[0])
    total = sum_saved+sum_bad+sum_no_content

print(f"Total number of analysed repos: {total}")
print(f"Total number of saved repos: {sum_saved} ({sum_saved/total * 100:.2f}%)")
print(f"Total number of discarded (bad) repos: {sum_bad} ({sum_bad/total * 100:.2f}%)")
print(f"Total number of discarded (no content) repos: {sum_no_content} ({sum_no_content/total * 100:.2f}%)")

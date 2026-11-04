"""Marketplace product analytics case: synthetic event funnel + A/B test.

No real Avito users or measurements are used.  Execute: python analysis.py
"""
from __future__ import annotations

import csv
import json
import math
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA, OUTPUT, SQL = ROOT / 'data', ROOT / 'output', ROOT / 'sql'
CATEGORIES = ('Электроника', 'Одежда', 'Дом и ремонт', 'Авто', 'Хобби')
REGIONS = ('Москва', 'Санкт-Петербург', 'Казань', 'Новосибирск')
START = datetime(2026, 9, 1, 12, 0)


def save_csv(path: Path, cols: tuple[str, ...] | list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


def generate(n_users: int = 20000, seed: int = 2026) -> dict:
    """Simulate independent users and intentionally inject logging defects."""
    if n_users < 100 or n_users % 2:
        raise ValueError('Number of users must be even and >= 100')
    rng = random.Random(seed)
    DATA.mkdir(parents=True, exist_ok=True)
    users, assignments, events = [], [], []
    listings = [{'listing_id': i, 'category': rng.choice(CATEGORIES),
                 'price_rub': rng.randrange(500, 100000, 100)} for i in range(1, 501)]
    variants = ['A'] * (n_users // 2) + ['B'] * (n_users // 2)
    rng.shuffle(variants)
    event_counter = 0

    def event(user: int, listing: int, kind: str, timestamp: datetime) -> None:
        nonlocal event_counter
        event_counter += 1
        events.append({'event_id': f'e{event_counter:09d}', 'user_id': user,
                       'listing_id': listing, 'event_type': kind,
                       'event_at': timestamp.isoformat(timespec='seconds')})

    no_contacts = []
    for index in range(n_users):
        uid = 100001 + index
        listing = rng.choice(listings)
        variant = variants[index]
        assigned = START + timedelta(days=rng.randrange(14), minutes=rng.randrange(720))
        users.append({'user_id': uid, 'region': rng.choice(REGIONS),
                      'device': rng.choices(('Android', 'iOS', 'Web'), weights=(50, 30, 20))[0]})
        assignments.append({'user_id': uid, 'listing_id': listing['listing_id'],
                            'variant': variant, 'assigned_at': assigned.isoformat(timespec='seconds')})
        exposure = assigned + timedelta(seconds=1)
        event(uid, listing['listing_id'], 'exposure', exposure)
        if rng.random() < 0.73:
            viewed = exposure + timedelta(seconds=rng.randrange(5, 50))
            event(uid, listing['listing_id'], 'listing_view', viewed)
            # Treatment B raises the conditional probability of contacting the seller.
            p_contact = 0.26 if variant == 'A' else 0.31
            if rng.random() < p_contact:
                contact = viewed + timedelta(seconds=rng.randrange(10, 190))
                event(uid, listing['listing_id'], 'contact_click', contact)
                if rng.random() < 0.55:
                    event(uid, listing['listing_id'], 'message_sent',
                          contact + timedelta(seconds=rng.randrange(5, 180)))
            else:
                no_contacts.append((uid, listing['listing_id'], viewed))
            if rng.random() < 0.008:
                event(uid, listing['listing_id'], 'complaint', viewed + timedelta(minutes=10))
        else:
            no_contacts.append((uid, listing['listing_id'], exposure))
        if rng.random() < 0.019:
            event(uid, listing['listing_id'], 'ui_error', exposure + timedelta(minutes=5))

    real_events = events[:]
    duplicates = max(1, n_users // 200)
    events.extend(x.copy() for x in rng.sample(real_events, duplicates))
    unknown = max(1, n_users // 2000)
    for i in range(unknown):
        event(900000 + i, 1, 'listing_view', START + timedelta(days=2))
    premature = max(1, n_users // 2500)
    for item in rng.sample(assignments, premature):
        event(item['user_id'], item['listing_id'], 'contact_click',
              datetime.fromisoformat(item['assigned_at']) - timedelta(minutes=5))
    orphans = max(1, n_users // 1800)
    for uid, lid, at in rng.sample(no_contacts, orphans):
        event(uid, lid, 'message_sent', at + timedelta(minutes=5))
    rng.shuffle(events)

    save_csv(DATA / 'users.csv', ('user_id', 'region', 'device'), users)
    save_csv(DATA / 'listings.csv', ('listing_id', 'category', 'price_rub'), listings)
    save_csv(DATA / 'assignments.csv', ('user_id', 'listing_id', 'variant', 'assigned_at'), assignments)
    save_csv(DATA / 'raw_events.csv', ('event_id', 'user_id', 'listing_id', 'event_type', 'event_at'), events)
    return {'users': len(users), 'raw_events': len(events),
            'duplicates_injected': duplicates, 'unknown_users_injected': unknown,
            'premature_events_injected': premature, 'orphan_messages_injected': orphans}


SCHEMA = '''
CREATE TABLE users(user_id INTEGER PRIMARY KEY, region TEXT, device TEXT);
CREATE TABLE listings(listing_id INTEGER PRIMARY KEY, category TEXT, price_rub INTEGER);
CREATE TABLE assignments(user_id INTEGER PRIMARY KEY, listing_id INTEGER, variant TEXT, assigned_at TEXT);
CREATE TABLE raw_events(event_id TEXT, user_id INTEGER, listing_id INTEGER, event_type TEXT, event_at TEXT);
CREATE INDEX ix_raw_event_id ON raw_events(event_id);
CREATE INDEX ix_raw_user ON raw_events(user_id);
'''
COLS = {'users': ('user_id', 'region', 'device'),
        'listings': ('listing_id', 'category', 'price_rub'),
        'assignments': ('user_id', 'listing_id', 'variant', 'assigned_at'),
        'raw_events': ('event_id', 'user_id', 'listing_id', 'event_type', 'event_at')}


def build_db(path: Path) -> sqlite3.Connection:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    for table, columns in COLS.items():
        with (DATA / (table + '.csv')).open(encoding='utf-8', newline='') as file:
            rows = [tuple(record[key] for key in columns) for record in csv.DictReader(file)]
        conn.executemany(f'INSERT INTO {table} VALUES ({",".join("?" for _ in columns)})', rows)
    conn.commit()
    for sql_file in ('01_clean.sql', '02_mart.sql'):
        conn.executescript((SQL / sql_file).read_text(encoding='utf-8'))
    return conn


def query(conn: sqlite3.Connection, name: str) -> list[dict]:
    return [dict(x) for x in conn.execute((SQL / name).read_text(encoding='utf-8'))]


def proportions(s_a: int, n_a: int, s_b: int, n_b: int) -> dict:
    """Unpooled 95% CI for B-A; pooled 2-sided z-test for H0: pA = pB."""
    if n_a <= 0 or n_b <= 0 or not 0 <= s_a <= n_a or not 0 <= s_b <= n_b:
        raise ValueError('Invalid successes or sample sizes')
    p_a, p_b = s_a / n_a, s_b / n_b
    delta = p_b - p_a
    pooled = (s_a + s_b) / (n_a + n_b)
    se0 = math.sqrt(pooled * (1 - pooled) * (1 / n_a + 1 / n_b))
    p_value = math.erfc(abs(delta / se0) / math.sqrt(2)) if se0 else 1.0
    se_ci = math.sqrt(p_a * (1 - p_a) / n_a + p_b * (1 - p_b) / n_b)
    return {'rate_a': p_a, 'rate_b': p_b, 'absolute_change': delta,
            'relative_change': delta / p_a if p_a else None,
            'ci95_lower': delta - 1.95996398454 * se_ci,
            'ci95_upper': delta + 1.95996398454 * se_ci,
            'p_value': p_value}


def srm_test(n_a: int, n_b: int) -> dict:
    """Sample-ratio mismatch chi-square test against expected 50/50 split."""
    n = n_a + n_b
    if n <= 0:
        raise ValueError('Empty test')
    chi2 = (n_a - n / 2) ** 2 / (n / 2) + (n_b - n / 2) ** 2 / (n / 2)
    p_value = math.erfc(math.sqrt(chi2 / 2))
    return {'chi2': chi2, 'p_value': p_value, 'srm_flag_p_lt_0_001': p_value < 0.001}


def plot_charts(metrics: list[dict], daily: list[dict]) -> None:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    groups = {x['variant']: x for x in metrics}
    steps = ('exposed', 'viewed', 'contacted', 'messaged')
    names = ('Экспозиция', 'Карточка', 'Контакт', 'Сообщение')
    fig, ax = plt.subplots(figsize=(8.2, 4.5))
    for group in ('A', 'B'):
        row = groups[group]
        ax.plot(names, [100 * row[k] / row['exposed'] for k in steps], marker='o', label=group)
    ax.set(title='Воронка: по отношению к экспозиции', ylabel='Конверсия от экспозиции, %', ylim=(0, 105))
    ax.grid(alpha=0.2)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUTPUT / 'funnel.png', dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.8, 4))
    vals = [groups[v]['contact_conversion_pct'] for v in ('A', 'B')]
    bars = ax.bar(['A: контроль', 'B: изменение'], vals)
    for bar in bars:
        ax.annotate(f'{bar.get_height():.2f}%', (bar.get_x() + bar.get_width() / 2,
                    bar.get_height()), ha='center', xytext=(0, 4), textcoords='offset points')
    ax.set(title='Контакт с продавцом — основная метрика', ylabel='Доля экспонированных, %',
           ylim=(0, max(vals) * 1.2))
    ax.grid(axis='y', alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUTPUT / 'ab_result.png', dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.2, 4.5))
    days = sorted(set(x['day'] for x in daily))
    for variant in ('A', 'B'):
        matching = {x['day']: x['conversion_pct'] for x in daily if x['variant'] == variant}
        ax.plot(days, [matching[d] for d in days], marker='.', label=variant)
    ax.set(title='Конверсия по дневным когортам', ylabel='Контакт / экспозиция, %')
    ax.grid(alpha=0.2)
    ax.legend()
    ax.tick_params(axis='x', rotation=40)
    fig.tight_layout()
    fig.savefig(OUTPUT / 'daily_conversion.png', dpi=150)
    plt.close(fig)


def run(n_users: int = 20000, seed: int = 2026) -> dict:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    generated = generate(n_users, seed)
    conn = build_db(OUTPUT / 'analytics.sqlite')
    files = {'metrics': '03_ab_metrics.sql', 'segments': '04_segments.sql',
             'daily': '05_daily.sql', 'quality': '06_quality.sql'}
    data = {name: query(conn, file) for name, file in files.items()}
    for name, rows in data.items():
        save_csv(OUTPUT / f'{name}.csv', list(rows[0]), rows)
    a, b = data['metrics']
    primary = proportions(a['contacted'], a['exposed'], b['contacted'], b['exposed'])
    secondary = proportions(a['messaged'], a['exposed'], b['messaged'], b['exposed'])
    error = proportions(a['ui_error'], a['exposed'], b['ui_error'], b['exposed'])
    complaint = proportions(a['complaints'], a['exposed'], b['complaints'], b['exposed'])
    srm = srm_test(a['exposed'], b['exposed'])
    result = {'dataset': 'synthetic demonstration only', 'generated': generated,
              'groups': data['metrics'], 'quality': data['quality'],
              'contact_test': primary, 'message_test': secondary,
              'ui_error_test': error, 'complaint_test': complaint, 'srm': srm}
    (OUTPUT / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    plot_charts(data['metrics'], data['daily'])

    p = lambda n: f'{100 * n:.2f}%'
    quality = {x['issue']: x['n'] for x in data['quality']}
    report = f'''# Кейс: воронка маркетплейса и A/B-тест

> **Учебный проект на синтетических данных. Это НЕ результаты реального маркетплейса.** Эффект B специально заложен в генератор.

## Гипотеза и метод
Изменённая карточка объявления (B) повысит долю пользователей, которые нажали «Связаться с продавцом».
Рандомизация по уникальному пользователю, 50/50. Деноминатор = все пользователи, получившие экспозицию.

**Основная метрика:** пользователи с `contact_click` / пользователи с `exposure`.
**Дополнительная метрика:** пользователи с `message_sent` / пользователи с `exposure`.
**Защитные метрики:** UI-ошибка и жалоба на пользователя.

## Проверка событий
- Сырых событий: **{generated['raw_events']:,}**; пользователи: **{n_users:,}**.
- Дубли `event_id`: **{quality['duplicate_event_ids']}**.
- События от неизвестных пользователей: **{quality['unknown_users']}**.
- События до назначения группы: **{quality['events_before_assignment']}**.
- Сообщения без предыдущего контакта: **{quality['orphan_messages']}**.

При расчёте исключены невалидные события; шаги воронки учитываются только по времени в верном порядке.

## Результаты
| Показатель | A | B |
|---|---:|---:|
| Экспонированные пользователи | {a['exposed']:,} | {b['exposed']:,} |
| Просмотр объявления | {a['viewed']:,} | {b['viewed']:,} |
| Контакт с продавцом | {a['contacted']:,} | {b['contacted']:,} |
| **Конверсия в контакт** | **{p(primary['rate_a'])}** | **{p(primary['rate_b'])}** |
| Конверсия в сообщение | {p(secondary['rate_a'])} | {p(secondary['rate_b'])} |
| UI-ошибки | {p(error['rate_a'])} | {p(error['rate_b'])} |
| Жалобы | {p(complaint['rate_a'])} | {p(complaint['rate_b'])} |

- Изменение конверсии B−A: **{100*primary['absolute_change']:+.2f} п.п.**.
- Относительное изменение: **{p(primary['relative_change'])}**.
- Двусторонний z-тест для двух долей: **p = {primary['p_value']:.4g}**.
- 95% доверительный интервал разницы: **[{100*primary['ci95_lower']:+.2f}; {100*primary['ci95_upper']:+.2f}] п.п.**.
- Проверка SRM (ожидаем 50/50): **p = {srm['p_value']:.4g}**.
- P-value сообщений: {secondary['p_value']:.4g}; ошибок: {error['p_value']:.4g}; жалоб: {complaint['p_value']:.4g}.

## Вывод
{'В симуляции разница по основной метрике статистически значима на уровне 5%.' if primary['p_value'] < 0.05 else 'В симуляции разница по основной метрике незначима на уровне 5%.'}
Это **не основание** выкатывать изменение в реальном продукте: данные синтетические. Для настоящего эксперимента
нужны заранее зафиксированные длительность, MDE, мощность, стратегия остановки и анализ качества рандомизации.
Необнаружение изменений в защитных метриках **не доказывает** их безопасности.
Сегментация по категориям исследовательская, без заявлений о значимости множественных проверок.

## Визуализация
![Воронка](funnel.png)
![Основная метрика](ab_result.png)
![Динамика](daily_conversion.png)
'''
    (OUTPUT / 'report.md').write_text(report, encoding='utf-8')
    conn.close()
    return result


if __name__ == '__main__':
    res = run()
    a, b = res['groups']
    x = res['contact_test']
    print(f"Users: {res['generated']['users']}; A contact={a['contact_conversion_pct']}%; B contact={b['contact_conversion_pct']}%")
    print(f"Uplift: {100*x['absolute_change']:+.2f} pp; 95% CI [{100*x['ci95_lower']:+.2f}; {100*x['ci95_upper']:+.2f}] pp; p={x['p_value']:.4g}")
    print('Full report: output/report.md')

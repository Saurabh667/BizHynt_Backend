import pymysql

def init_schema():
    conn = pymysql.connect(
        host='127.0.0.1',
        user='root',
        password='Yadav@1977',
        port=3306
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES FROM rts_lead_tracker;")
            tables = [r[0] for r in cursor.fetchall() if not r[0].startswith('django_') and not r[0].startswith('auth_') and r[0] != '_prisma_migrations']
            
            print(f"Found {len(tables)} tables to replicate in sales_generator...")

            cursor.execute("USE sales_generator;")
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")

            for t in tables:
                cursor.execute(f"SHOW CREATE TABLE rts_lead_tracker.{t};")
                create_stmt = cursor.fetchone()[1]
                # Replace CREATE TABLE with CREATE TABLE IF NOT EXISTS
                create_stmt = create_stmt.replace(f"CREATE TABLE `{t}`", f"CREATE TABLE IF NOT EXISTS `{t}`")
                cursor.execute(create_stmt)
                print(f"  [OK] Created table: {t}")

            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
            conn.commit()
            print("\nSchema initialization in 'sales_generator' completed successfully!")

    finally:
        conn.close()

if __name__ == '__main__':
    init_schema()

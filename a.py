import pymysql
import re
from g4f.client import Client
import base64

# 初始化 Groq 客戶端
def connect_to_database():
    pwString = "QVZOU18zQ0ZFcG9lRnlFRU4zX2VvUThL"
    pwBytes = base64.b64decode(pwString)
    pw = pwBytes.decode('utf-8')
    print("正在連接資料庫...")
    return pymysql.connect(
        host='mysql-1bddf0d4-davis1233798-2632.d.aivencloud.com', 
        port=20946, user='avnadmin',
         password=pw, database='defaultdb', charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)

def clean_text(input_text):
    cleaned_text = re.sub(r'[^\u0000-\uFFFF]', '', input_text)
    print(f"清理後的文字: {cleaned_text}")
    return cleaned_text

def reset_is_taken_if_needed(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS count FROM prompts WHERE is_taken = 1")
        count_result = cursor.fetchone()
        if count_result['count'] > 20:
            print("is_taken = 1的數量超過20，正在重設...")
            cursor.execute("UPDATE prompts SET is_taken = 0")
            connection.commit()
            print("所有is_taken已重設為0。")

def get_next_prompt(connection):
    with connection.cursor() as cursor:
        for i in range(1, 21):
            field_name = f"result{i}"
            cursor.execute(f"""
                SELECT prompts.id FROM prompts
                INNER JOIN gpt4_judged_final ON prompts.id = gpt4_judged_final.prompts_id
                WHERE prompts.is_taken = 0 AND gpt4_judged_final.{field_name} IS NULL
                ORDER BY prompts.id ASC
                LIMIT 1
            """)
            result = cursor.fetchone()
            if result:
                prompt_id = result['id']
                cursor.execute("UPDATE prompts SET is_taken = 1 WHERE id = %s", (prompt_id,))
                connection.commit()
                print(f"獲得並設置提示ID {prompt_id} 的 is_taken 為1，欄位：{field_name}")
                return {'id': prompt_id, 'field_name': field_name}
        print("沒有可用的提示ID或空缺欄位")
        reset_is_taken_if_needed(connection)
        return None


def update_field(connection, prompt_id, field_name, decision):
    with connection.cursor() as cursor:
        cursor.execute(f"UPDATE gpt4_judged_final SET {field_name} = %s WHERE prompts_id = %s AND {field_name} IS NULL", (decision, prompt_id))
        connection.commit()
        print(f"gpt4_judged_final表更新成功，ID {prompt_id}，欄位：{field_name}")


def process_prompts():
    client = Client()
    connection = connect_to_database()
    try:
        while True:
            prompt_info = get_next_prompt(connection)
            if not prompt_info:
                print("檢查後仍無可用提示或空缺欄位，程式將結束。")
                break
            prompt_id = prompt_info['id']
            field_name = prompt_info['field_name']
            cursor = connection.cursor()
            cursor.execute("SELECT p.trained_result, d.value as description FROM prompts p JOIN descriptions d ON p.cve_id = d.cve_id WHERE p.id = %s", (prompt_id,))
            result = cursor.fetchone()
            content = f"請您實際的使用\n1.修補方法: {result['trained_result']} 來修補\n2.漏洞: {result['description']} 確認實作修補策略是否可修補這個漏洞\n3.只需要回答是或否即可。"
            response = client.chat.completions.create(model="gpt-4-turbo", messages=[{"role": "user", "content": content}])
            decision = clean_text(response.choices[0].message.content)
            print(decision)
            update_field(connection, prompt_id, field_name, decision)
            reset_is_taken_if_needed(connection)
    except Exception as e:
        print(f"發生錯誤：{str(e)}")
    finally:
        if connection and connection.open:
            connection.close()

process_prompts()

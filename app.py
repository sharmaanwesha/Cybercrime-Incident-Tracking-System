
from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
from datetime import datetime, date, timedelta
from flask import jsonify

app = Flask(__name__)
CORS(app)

def get_db_connection():
    conn = mysql.connector.connect(
        host="localhost",
        user="root",              
        password="Teddy@1805", 
        database="cits_db"
    )
    return conn

@app.route('/api/register', methods=['POST'])
def register_citizen():
    data = request.json

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Prepare arguments (IN + OUT)
        args = [
            data['name'],
            data['email'],
            data['password'],
            data['phone'],
            data['address'],
            data['city'],
            '',   
            ''    
        ]

        result_args = cursor.callproc('register_citizen', args)
        conn.commit()

        citizen_id = result_args[6]
        status = result_args[7]

        cursor.close()
        conn.close()

        if status == 'SUCCESS':
            return jsonify({
                'success': True,
                'message': 'Registration successful',
                'citizen_id': citizen_id
            }), 201
        elif status == 'EMAIL_EXISTS':
            return jsonify({
                'success': False,
                'message': 'Email already registered'
            }), 400
        elif status == 'ERROR':
            return jsonify({
                'success': False,
                'message': 'Database error occurred'
            }), 500
        else:
            return jsonify({
                'success': False,
                'message': f'Unexpected status: {status}'
            }), 500

    except Exception as e:
        print("❌ Registration Error:", e)
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500



@app.route('/api/login', methods=['POST'])
def login_citizen():
    data = request.json
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Simple query to check credentials
        cursor.execute("""
            SELECT citizen_id, full_name, email, phone, address, city
            FROM citizens
            WHERE email = %s AND password = %s
        """, (data['email'], data['password']))
        
        citizen = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if citizen:
            return jsonify({
                'success': True,
                'message': 'Login successful',
                'citizen': citizen
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Invalid email or password'
            }), 401
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/file-complaint', methods=['POST'])
def file_complaint():
    data = request.json
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Prepare IN + OUT args
        args = [
            data['citizen_id'],
            data['crime_type'],
            data['incident_date'],
            data.get('incident_time'),
            data['description'],
            data.get('financial_loss', 0),
            data['urgency'],
            data.get('suspect_info', ''),
            '',   # OUT case_id
            ''    # OUT status
        ]

        result_args = cursor.callproc('file_complaint', args)

        conn.commit()

        case_id = result_args[8]
        status = result_args[9]

        if status == 'SUCCESS' and 'evidence' in data and data['evidence']:
            for file_info in data['evidence']:
                cursor.execute("""
                    INSERT INTO evidence (case_id, file_name, file_type)
                    VALUES (%s, %s, %s)
                """, (case_id, file_info['name'], file_info['type']))
            conn.commit()

        cursor.close()
        conn.close()

        if status == 'SUCCESS':
            return jsonify({
                'success': True,
                'message': 'Complaint filed successfully',
                'case_id': case_id
            }), 201
        elif status == 'ERROR':
            return jsonify({
                'success': False,
                'message': 'Database error occurred'
            }), 500
        else:
            return jsonify({
                'success': False,
                'message': f'Failed to file complaint (status={status})'
            }), 500

    except Exception as e:
        print("❌ Complaint Error:", e)
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/complaints/<citizen_id>', methods=['GET'])
def get_complaints(citizen_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
    
        cursor.callproc('get_citizen_complaints', [citizen_id])
        
        complaints = []
        for result in cursor.stored_results():
            complaints = result.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'complaints': complaints
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/complaint/<case_id>', methods=['GET'])
def get_complaint_details(case_id):
    try:
        print("🔍 DEBUG - Received case_id:", case_id)

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
                c.*, 
                o.full_name AS officer_name, 
                o.badge_number AS officer_badge,
                o.department AS officer_department,
                o.phone AS officer_phone
            FROM complaints c
            LEFT JOIN officers o ON c.assigned_officer_id = o.officer_id
            WHERE LOWER(c.case_id) = LOWER(%s)
        """, (case_id,))
        complaint = cursor.fetchone()
        print("Complaint fetched:", complaint)

        if not complaint:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Complaint not found'}), 404

        
        for key, value in complaint.items():
            if isinstance(value, (datetime, )):
                complaint[key] = value.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(value, timedelta):
                # convert timedelta (e.g. 02:03:00) to readable string
                total_seconds = int(value.total_seconds())
                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                complaint[key] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

       
        cursor.execute("""
            SELECT * FROM case_history
            WHERE LOWER(case_id) = LOWER(%s)
            ORDER BY timestamp ASC
        """, (case_id,))
        history = cursor.fetchall()

        
        for h in history:
            for k, v in h.items():
                if isinstance(v, datetime):
                    h[k] = v.strftime("%Y-%m-%d %H:%M:%S")

        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'complaint': complaint,
            'history': history
        }), 200

    except Exception as e:
        print("❌ ERROR in /api/complaint/<case_id>:", e)
        return jsonify({'success': False, 'message': str(e)}), 500




@app.route('/api/dashboard/<citizen_id>', methods=['GET'])
def get_dashboard_stats(citizen_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get complaint statistics
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'Under Investigation' THEN 1 ELSE 0 END) as investigating,
                SUM(CASE WHEN status = 'Closed' THEN 1 ELSE 0 END) as closed
            FROM complaints
            WHERE citizen_id = %s
        """, (citizen_id,))
        
        stats = cursor.fetchone()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'stats': stats
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/audit-log', methods=['GET'])
def get_audit_log():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT * FROM audit_log
            ORDER BY action_timestamp DESC
            LIMIT 50
        """)
        
        logs = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'logs': logs
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/test', methods=['GET'])
def test_connection():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 'Database connected!' as message")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': result[0]
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
    


@app.route('/api/officer-login', methods=['POST'])
def officer_login():
    data = request.json
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        args = [
            data['email'],
            data['password'],
            '',   # OUT officer_id
            ''    # OUT status
        ]
        
        result_args = cursor.callproc('officer_login', args)
        conn.commit()
        
        officer_id = result_args[2]
        status = result_args[3]
        
        cursor.close()
        
        if status == 'SUCCESS':
            # Get officer details
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT officer_id, full_name, email, phone, badge_number, 
                       department, officer_rank, assigned_cases
                FROM officers
                WHERE officer_id = %s
            """, (officer_id,))
            
            officer = cursor.fetchone()
            cursor.close()
            conn.close()
            
            return jsonify({
                'success': True,
                'message': 'Login successful',
                'officer': officer
            }), 200
        else:
            conn.close()
            return jsonify({
                'success': False,
                'message': 'Invalid email or password'
            }), 401
            
    except Exception as e:
        print("❌ Officer Login Error:", e)
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/officer/cases/<officer_id>', methods=['GET'])
def get_officer_cases(officer_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
       
        cursor.callproc('get_officer_cases', [officer_id])
        
       
        cases = []
        for result in cursor.stored_results():
            cases = result.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'cases': cases
        }), 200
        
    except Exception as e:
        print("❌ Get Cases Error:", e)
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/officer/update-status', methods=['POST'])
def update_case_status():
    data = request.json
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
    
        args = [
            data['case_id'],
            data['officer_id'],
            data['new_status'],
            data.get('note', ''),
            ''    # OUT result
        ]
        
        
        result_args = cursor.callproc('update_case_status', args)
        conn.commit()
        
        result = result_args[4]
        
        cursor.close()
        conn.close()
        
        if result == 'SUCCESS':
            return jsonify({
                'success': True,
                'message': 'Case status updated successfully'
            }), 200
        elif result == 'UNAUTHORIZED':
            return jsonify({
                'success': False,
                'message': 'You are not authorized to update this case'
            }), 403
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to update case status'
            }), 500
            
    except Exception as e:
        print("❌ Update Status Error:", e)
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/officer/add-note', methods=['POST'])
def add_case_note():
    data = request.json
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Prepare IN + OUT args
        args = [
            data['case_id'],
            data['officer_id'],
            data['note_text'],
            ''    # OUT result
        ]
        
        # Call stored procedure
        result_args = cursor.callproc('add_case_note', args)
        conn.commit()
        
        result = result_args[3]
        
        cursor.close()
        conn.close()
        
        if result == 'SUCCESS':
            return jsonify({
                'success': True,
                'message': 'Note added successfully'
            }), 201
        elif result == 'UNAUTHORIZED':
            return jsonify({
                'success': False,
                'message': 'You are not authorized to add notes to this case'
            }), 403
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to add note'
            }), 500
            
    except Exception as e:
        print("❌ Add Note Error:", e)
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/officer/notes/<case_id>', methods=['GET'])
def get_case_notes(case_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT cn.*, o.full_name as officer_name
            FROM case_notes cn
            JOIN officers o ON cn.officer_id = o.officer_id
            WHERE cn.case_id = %s
            ORDER BY cn.created_at DESC
        """, (case_id,))
        
        notes = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'notes': notes
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/officer/dashboard/<officer_id>', methods=['GET'])
def get_officer_dashboard_stats(officer_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # ✅ Ensure officer_id is treated as integer
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'Under Investigation' THEN 1 ELSE 0 END) as investigating,
                SUM(CASE WHEN status = 'Closed' THEN 1 ELSE 0 END) as closed
            FROM complaints
            WHERE assigned_officer_id = CAST(%s AS UNSIGNED)
        """, (officer_id,))

        stats = cursor.fetchone()
        cursor.close()
        conn.close()

        if not stats or stats['total'] is None:
            stats = {'total': 0, 'pending': 0, 'investigating': 0, 'closed': 0}

        return jsonify({'success': True, 'stats': stats}), 200

    except Exception as e:
        print("❌ Officer Dashboard Error:", e)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/available-officers', methods=['GET'])
def get_available_officers():
    """Check how many officers are available for assignment (have less than 5 cases)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Count officers with less than 5 cases
        cursor.execute("""
            SELECT COUNT(*) as available_count
            FROM officers
            WHERE is_active = TRUE AND assigned_cases < 5
        """)
        
        result = cursor.fetchone()
        available_count = result[0] if result else 0
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'available_officers': available_count
        }), 200
        
    except Exception as e:
        print("❌ Available Officers Error:", e)
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/officer-workload', methods=['GET'])
def get_officer_workload():
    """View all officers and their current workload"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT * FROM officer_workload")
        
        workload = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'workload': workload
        }), 200
        
    except Exception as e:
        print("❌ Workload Error:", e)
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
    
@app.route('/api/admin/complaint/<case_id>', methods=['GET'])
def admin_get_complaint(case_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT c.case_id, c.crime_type, c.description, c.financial_loss, c.status, 
                   c.urgency, cit.full_name AS citizen_name, cit.email AS citizen_email,
                   cit.phone AS citizen_phone, cit.address, o.full_name AS officer_name
            FROM complaints c
            JOIN citizens cit ON c.citizen_id = cit.citizen_id
            LEFT JOIN officers o ON c.assigned_officer_id = o.officer_id
            WHERE c.case_id = %s
        """, (case_id,))
        complaint = cursor.fetchone()
        cursor.close()
        conn.close()

        if complaint:
            return jsonify({'success': True, 'complaint': complaint}), 200
        else:
            return jsonify({'success': False, 'message': 'Complaint not found'}), 404

    except Exception as e:
        print("❌ Admin Complaint Fetch Error:", e)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin-login', methods=['POST'])
def admin_login():
    data = request.json
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        args = [data['email'], data['password'], '', '']
        result = cursor.callproc('admin_login', args)
        admin_id = result[2]
        status = result[3]

        cursor.close()
        conn.close()

        if status == 'SUCCESS':
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT admin_id, full_name, email, role, is_active FROM admins WHERE admin_id=%s", (admin_id,))
            admin = cur.fetchone()
            cur.close()
            conn.close()
            return jsonify({'success': True, 'admin': admin}), 200
        else:
            return jsonify({'success': False, 'message': 'Invalid email or password'}), 401

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/overview', methods=['GET'])
def admin_overview():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.callproc('admin_overview_stats')
        for result in cursor.stored_results():
            stats = result.fetchone()
        cursor.close()
        conn.close()
        return jsonify({'success': True, 'stats': stats}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/officers', methods=['GET'])
def admin_officers():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.callproc('get_officer_workload')

        officers = []
        for result in cursor.stored_results():
            officers = result.fetchall()

        # 🔍 Normalize and debug log
        for o in officers:
            raw = o.get('is_active', 0)
            o['is_active'] = True if str(raw) in ('1', 'True', 'true', 't', 'yes') or raw == 1 else False
            print(f"Officer {o.get('officer_id')} raw={raw} normalized={o['is_active']}")

        cursor.close()
        conn.close()
        return jsonify({'success': True, 'officers': officers}), 200

    except Exception as e:
        print("❌ Admin Officers Error:", e)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/citizens', methods=['GET'])
def admin_citizens():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT citizen_id, full_name, email, phone, city, address FROM citizens")
        citizens = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify({'success': True, 'citizens': citizens}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/complaints', methods=['GET'])
def admin_complaints():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Call stored procedure
        cursor.callproc('get_all_complaints_cursor')

        complaints = []
        for result in cursor.stored_results():
            complaints = result.fetchall()

        # ✅ Fix timedelta or null issues
        for comp in complaints:
            for k, v in comp.items():
                if isinstance(v, timedelta):
                    comp[k] = str(v)
                elif v is None:
                    comp[k] = "-"

        cursor.close()
        conn.close()

        return jsonify({'success': True, 'complaints': complaints}), 200

    except Exception as e:
        print("❌ Admin Complaints Error:", e)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/case-history/<case_id>', methods=['GET'])
def get_case_history(case_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT previous_officer, new_officer, changed_by, action_type, timestamp
            FROM case_history
            WHERE case_id = %s
            ORDER BY timestamp ASC
        """, (case_id,))
        history = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify({'success': True, 'history': history}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/toggle-officer', methods=['POST'])
def toggle_officer():
    data = request.json
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get current status
        cursor.execute("SELECT is_active FROM officers WHERE officer_id = %s", (data['officer_id'],))
        current = cursor.fetchone()

        if not current:
            return jsonify({'success': False, 'message': 'Officer not found'}), 404

        # Toggle active status
        new_status = 0 if current['is_active'] == 1 else 1
        cursor.execute("UPDATE officers SET is_active = %s WHERE officer_id = %s", (new_status, data['officer_id']))

        # 🔁 Auto reassign cases if officer is being deactivated
        if new_status == 0:
            # Find another active officer with least workload
            cursor.execute("""
                SELECT officer_id
                FROM officers
                WHERE is_active = 1
                ORDER BY assigned_cases ASC
                LIMIT 1
            """)
            replacement = cursor.fetchone()

            if replacement:
                cursor.execute("""
                    UPDATE complaints
                    SET assigned_officer_id = %s
                    WHERE assigned_officer_id = %s AND status != 'Closed'
                """, (replacement['officer_id'], data['officer_id']))

                # Update workload counters
                cursor.execute("""
                    UPDATE officers
                    SET assigned_cases = assigned_cases + (
                        SELECT COUNT(*) FROM complaints WHERE assigned_officer_id = %s
                    )
                    WHERE officer_id = %s
                """, (replacement['officer_id'], replacement['officer_id']))

                cursor.execute("""
                    UPDATE officers
                    SET assigned_cases = 0
                    WHERE officer_id = %s
                """, (data['officer_id'],))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': 'Officer status updated successfully'}), 200

    except Exception as e:
        print("❌ Toggle Officer Error:", e)
        return jsonify({'success': False, 'message': str(e)}), 500
    
@app.route('/api/admin/cases', methods=['GET'])
def admin_cases():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.callproc('get_all_complaints_cursor')
        cases = []
        for result in cursor.stored_results():
            cases = result.fetchall()

        cursor.close()
        conn.close()

        return jsonify({'success': True, 'cases': cases}), 200
    except Exception as e:
        print("❌ Admin Cases Error:", e)
        return jsonify({'success': False, 'message': str(e)}), 500
    
@app.route('/api/admin/update-case', methods=['POST'])
def admin_update_case():
    data = request.json
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE complaints 
            SET status = %s, assigned_officer_id = %s
            WHERE case_id = %s
        """, (data['new_status'], data['officer_id'], data['case_id']))

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'success': True, 'message': 'Case updated successfully'}), 200
    except Exception as e:
        print("❌ Admin Update Case Error:", e)
        return jsonify({'success': False, 'message': str(e)}), 500
    
@app.route('/api/admin/add-officer', methods=['POST'])
def add_officer():
    data = request.json
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO officers (full_name, email, password, phone, badge_number, department, officer_rank, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
        """, (data['full_name'], data['email'], data['password'], data['phone'], data['badge_number'], data['department'], data['officer_rank']))

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'success': True, 'message': 'Officer added successfully'}), 201

    except Exception as e:
        print("❌ Add Officer Error:", e)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/remove-officer', methods=['DELETE'])
def remove_officer():
    officer_id = request.args.get('officer_id')
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM officers WHERE officer_id = %s", (officer_id,))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': 'Officer removed successfully'}), 200

    except Exception as e:
        print("❌ Remove Officer Error:", e)
        return jsonify({'success': False, 'message': str(e)}), 500
    
@app.route('/api/admin/logs', methods=['GET'])
def get_recent_logs():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM audit_log 
            ORDER BY action_timestamp DESC 
            LIMIT 25
        """)
        logs = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify({'success': True, 'logs': logs}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    
@app.route('/api/admin/handle-complaint', methods=['POST'])
def admin_take_over():
    data = request.json
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Check if already handled by admin
        cursor.execute("SELECT handled_by_admin FROM complaints WHERE case_id = %s", (data['case_id'],))
        record = cursor.fetchone()
        if record and record['handled_by_admin'] == 1:
            return jsonify({'success': False, 'message': 'Case already handled by admin'}), 400

        # Get previous officer (if any)
        cursor.execute("SELECT assigned_officer_id FROM complaints WHERE case_id = %s", (data['case_id'],))
        prev = cursor.fetchone()
        previous_officer = prev['assigned_officer_id'] if prev and prev['assigned_officer_id'] else None

        # Reduce workload of old officer
        if previous_officer:
            cursor.execute("""
                UPDATE officers
                SET assigned_cases = assigned_cases - 1
                WHERE officer_id = %s AND assigned_cases > 0
            """, (previous_officer,))

        # Mark complaint handled by admin
        cursor.execute("""
            UPDATE complaints
            SET handled_by_admin = 1,
                assigned_officer_id = NULL,
                status = 'Admin Review'
            WHERE case_id = %s
        """, (data['case_id'],))

        # Log case takeover
        cursor.execute("""
            INSERT INTO case_history (case_id, previous_officer, new_officer, changed_by, action_type)
            VALUES (%s, %s, 'ADMIN', 'Admin', 'TAKEN_OVER')
        """, (data['case_id'], previous_officer))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': f'Case {data["case_id"]} taken over by admin'}), 200

    except Exception as e:
        print("❌ Admin Takeover Error:", e)
        return jsonify({'success': False, 'message': str(e)}), 500

    
@app.route('/api/admin/return-to-officer', methods=['POST'])
def admin_return_to_officer():
    data = request.json
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # previous handler: when Admin owns it, we log 'ADMIN'
        cursor.execute("SELECT assigned_officer_id, handled_by_admin FROM complaints WHERE case_id=%s", (data['case_id'],))
        row = cursor.fetchone()
        previous_officer = 'ADMIN' if row and row[1] == 1 else (row[0] or 'ADMIN')

        
        cursor.execute("""
            SELECT officer_id FROM officers
            WHERE is_active = 1
            ORDER BY assigned_cases ASC
            LIMIT 1
        """)
        pick = cursor.fetchone()
        if not pick:
            cursor.close(); conn.close()
            return jsonify({'success': False, 'message': 'No active officer available'}), 404

        new_officer = pick[0]

        
        cursor.execute("""
            UPDATE complaints
            SET assigned_officer_id = %s,
                handled_by_admin = 0,
                status = 'Under Investigation'
            WHERE case_id = %s
        """, (new_officer, data['case_id']))

        
        cursor.execute("""
            UPDATE officers SET assigned_cases = assigned_cases + 1
            WHERE officer_id = %s
        """, (new_officer,))

        
        cursor.execute("""
            INSERT INTO case_history (case_id, previous_officer, new_officer, changed_by, action_type)
            VALUES (%s, %s, %s, 'Admin', 'REASSIGNED')
        """, (data['case_id'], previous_officer, new_officer))

        conn.commit()
        cursor.close(); conn.close()
        return jsonify({'success': True, 'message': f'Case {data["case_id"]} reassigned to officer {new_officer}'}), 200
    except Exception as e:
        print("❌ Admin Return Error:", e)
        return jsonify({'success': False, 'message': str(e)}), 500
    
@app.route('/api/admin/review-cases', methods=['GET'])
def admin_review_cases():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT case_id, crime_type, urgency, status, filed_date
        FROM complaints
        WHERE handled_by_admin = 1
        ORDER BY filed_date DESC
    """)
    cases = cursor.fetchall()
    cursor.close()
    conn.close()

    return jsonify({'success': True, 'cases': cases}), 200

@app.route('/api/admin/update-complaint', methods=['POST'])
def admin_update_complaint():
    data = request.json
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE complaints
            SET crime_type = %s,
                description = %s,
                urgency = %s,
                financial_loss = %s,
                status = %s,
                suspect_info = %s,
                last_updated = NOW()
            WHERE case_id = %s
        """, (
            data.get('crime_type'),
            data.get('description'),
            data.get('urgency'),
            data.get('financial_loss'),
            data.get('status'),
            data.get('suspect_info'),
            data.get('case_id')
        ))
        conn.commit()

        # ✅ Log admin change in case history
        cursor.execute("""
            INSERT INTO case_history (case_id, previous_officer, new_officer, changed_by, action_type)
            VALUES (%s, 'ADMIN', 'ADMIN', 'Admin', 'UPDATED_CASE')
        """, (data.get('case_id'),))
        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': f'Case {data["case_id"]} updated successfully by Admin'}), 200

    except Exception as e:
        print("❌ Admin Update Error:", e)
        return jsonify({'success': False, 'message': str(e)}), 500



if __name__ == '__main__':
    app.run(debug=True, port=5000)

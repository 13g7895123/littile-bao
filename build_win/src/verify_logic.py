import sys
import unittest.mock as mock
from PyQt6.QtWidgets import QApplication, QMessageBox
import gui
import broker

def test_logic():
    app = QApplication.instance() or QApplication(sys.argv)
    win = gui.App()

    # Pre-fill required fields to avoid 'Incomplete fields' validation error
    f = win._bfields
    f["personal_id"].setText("test_id")
    f["password"].setText("test_pw")
    f["cert_path"].setText("test_cert")
    f["branch_no"].setText("test_branch")
    f["account_no"].setText("test_acc")

    # Mock QMessageBox to prevent blocking
    # Also mock _dispatch_ui to run synchronously during test
    win._dispatch_ui = lambda func: func()

    with mock.patch.object(QMessageBox, 'information'), \
         mock.patch.object(QMessageBox, 'critical'), \
         mock.patch('gui.push_log'):
        
        # Test Case 1: Failure path
        print("Running Test Case 1: Exception path...")
        with mock.patch('broker.FubonAdapter.from_config') as mock_from_config:
            mock_from_config.side_effect = Exception('boom')
            # Trigger the logic
            win._broker_test_connection()
            
            actual_text = win._broker_conn_lbl.text()
            if '錯誤：boom' in actual_text:
                print("SUCCESS: Case 1 passed.")
            else:
                print(f"FAILURE: Case 1 failed. Actual text: '{actual_text}'")
                sys.exit(1)

        # Test Case 2: Success path
        print("Running Test Case 2: Success path...")
        with mock.patch('broker.FubonAdapter.from_config') as mock_from_config:
            mock_inst = mock.Mock()
            # Success result object
            mock_result = mock.Mock()
            mock_result.success = True
            
            mock_acc = mock.Mock()
            mock_acc.display = '6460-1234567'
            mock_result.selected = mock_acc
            
            mock_inst.login.return_value = mock_result
            mock_from_config.return_value = mock_inst
            
            # Trigger the logic
            win._broker_test_connection()
            
            actual_text = win._broker_conn_lbl.text()
            if '連線成功：6460-1234567' in actual_text:
                print("SUCCESS: Case 2 passed.")
            else:
                print(f"FAILURE: Case 2 failed. Actual text: '{actual_text}'")
                sys.exit(1)

    print("\nAll tests passed successfully.")
    sys.exit(0)

if __name__ == "__main__":
    try:
        test_logic()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)

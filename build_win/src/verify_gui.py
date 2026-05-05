import sys
import threading
import time
from PyQt6.QtWidgets import QApplication
import gui

def run_test():
    app = QApplication.instance() or QApplication(sys.argv)
    win = gui.App()
    
    # Define the worker function
    def worker():
        try:
            time.sleep(1) # Wait a bit for the event loop to start
            # Using _dispatch_ui to run on main thread
            win._dispatch_ui(lambda: win._set_broker_page_status('測試完成', gui.C['green']))
            time.sleep(1)
            app.quit()
        except Exception as e:
            print(f"Worker Error: {e}")
            app.quit()

    thread = threading.Thread(target=worker)
    thread.start()

    # Run event loop for a short period
    app.exec()
    thread.join()

    # Check the result
    actual_text = win._broker_conn_lbl.text()
    print(f"DEBUG: Actual text is '{actual_text}'")
    if actual_text == '測試完成':
        print("SUCCESS: GUI update verified.")
        sys.exit(0)
    else:
        print(f"FAILURE: Expected '測試完成', but got '{actual_text}'")
        sys.exit(1)

if __name__ == "__main__":
    try:
        run_test()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)

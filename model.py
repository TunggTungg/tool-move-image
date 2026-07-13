import os
import shutil

class PhotoCopyModel:
    def __init__(self):
        pass

    def scan_images(self, src_root, allowed_types, stop_checker):
        """Quét và đếm toàn bộ file ảnh hợp lệ dựa trên cấu trúc thư mục"""
        files_to_copy = []
        for root, dirs, files in os.walk(src_root):
            if stop_checker():
                break
            current_folder_name = os.path.basename(root).lower()
            if current_folder_name in allowed_types:
                for file in files:
                    if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp')):
                        files_to_copy.append(os.path.join(root, file))
        return files_to_copy

    def copy_single_file(self, file_path, dest_root, stop_checker):
        """Thực hiện copy một file đơn lẻ và xử lý trùng tên"""
        if stop_checker():
            return "stopped", ""
        try:
            filename = os.path.basename(file_path)
            dest_path = os.path.join(dest_root, filename)

            base, extension = os.path.splitext(filename)
            counter = 1
            while os.path.exists(dest_path):
                dest_path = os.path.join(dest_root, f"{base}_{counter}{extension}")
                counter += 1

            shutil.copy2(file_path, dest_path)
            return "success", filename
        except Exception as e:
            return "error", f"{os.path.basename(file_path)} -> {str(e)}"

    def delete_all_files(self, dest_root):
        """Xóa sạch thư mục Output"""
        deleted_count = 0
        for filename in os.listdir(dest_root):
            file_path = os.path.join(dest_root, filename)
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
                deleted_count += 1
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
                deleted_count += 1
        return deleted_count
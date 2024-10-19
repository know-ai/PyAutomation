import os, logging

log_folder = os.path.join(".", "logs")
if not os.path.exists(log_folder):
    
    os.makedirs(log_folder)

log_file = os.path.join(log_folder, 'app.log')
log_format = "%(asctime)s:%(levelname)s:%(message)s"
level = logging.WARNING

if not log_file:
    
    logging.basicConfig(level=level, format=log_format)

else:

    logging.basicConfig(filename=log_file, level=level, format=log_format)
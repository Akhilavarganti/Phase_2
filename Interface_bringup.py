import os
import subprocess
import logging

class interface:
	
	def run_cmd(cmd):
		try:
			subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DevNULL)
			return True
		except subprocess.CalledProcessError:
			return False
			
	def is_config_enabled(param):
		try:
			with open(CONFIG_FILE, "r")as f:
				return any(line.strip() == param for line in f)
		except:
			return False
			
	def is_spi_enabled(self):
		try:
			result = subprocess.check_output("lsmod | grep spi_bcm2835", shell=True)
			return bool(result.strip())
		except subprocess.CalledProcessError:
			return False
			
	def is_i2c_enabled(self):
		try:
			result = subprocess.check_output("lsmod | grep i2c_bcm2835", shell=True)
			return bool(result.strip())
		except subprocess.CalledProcessError:
			return False
            
	def enable_spi():
		if is_config_enabled("dtparam=spi=on"):
			logging.info("-----Enabled SPI already")
		else:
			logging.info("Enabling SPI.....")
			run_cmd(["sudo", "raspi-config", "nonint", "do_spi", "0"])
	
	def enable_i2c():
		if is_config_enabled("dtparam=i2c=on"):
			logging.info("Enabled I2C already")
		else:
			logging.info("Enabling I2C.....")
			run_cmd(["sudo", "raspi-config", "nonint", "do_i2c", "0"])
			
	def ensure_interfaces_enabled(self):
		reboot_required = False
		if not self.is_spi_enabled():
			logging.warning("SPI not enabled. Enabling now...")
			self.enable_spi()
			reboot_required = True
		else:
			logging.info("SPI already enabled")
		
		if not self.is_i2c_enabled():
			logging.warning("I2C not enabled. Enabling now...")
			self.enable_i2c()
			reboot_required = True
			
		else:
			logging.info("I2C already enabled")

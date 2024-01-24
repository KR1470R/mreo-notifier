import time
import dotenv
import asyncio
from os import path, getenv, curdir
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.select import Select
from selenium.webdriver.chrome.options import Options
from aiogram import Bot, Dispatcher, types, Router
from aiogram.filters import Command
from aiogram.types import Message
import logging
import logging.config

dotenv.load_dotenv(path.abspath(
  path.join(curdir, "configs", ".env")
))

chat_ids = []
TOKEN_API = getenv("BOT_TOKEN_API")

filekey_path = getenv("FILEKEY_PATH")
key = None
with open(getenv("KEY_PATH")) as f:
  key = f.readline().strip()

options = Options()
options.add_argument('--headless=new')
service = Service(getenv("CHROMEDRIVER_PATH"))
driver = webdriver.Chrome(
  service=service, 
  options=options
)

class CustomAdapter(logging.LoggerAdapter):
  def process(self, msg, kwargs):
    # use my_context from kwargs or the default given on instantiation
    my_context = kwargs.pop('current_url', driver.current_url)
    return '[%s] %s' % (my_context, msg), kwargs

logger = logging.getLogger(__name__)
syslog = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s %(message)s')
syslog.setFormatter(formatter)
logger.addHandler(syslog)
adapter = CustomAdapter(logger, {'current_url': driver.current_url})
logger.setLevel(logging.INFO)

target_address = getenv("SERVICE_ADDRESS")
target_z_index = getenv("Z_INDEX_TARGET")
range_dates_admissions = int(getenv("RANGE_DATES_ADMISSIONS"))

class TicketsIcons:
  available = "https://eq.hsc.gov.ua/images/hsc_.png"
  available_online = "https://eq.hsc.gov.ua/images/hsc_i.png"
  available_offline = "https://eq.hsc.gov.ua/images/hsc_t.png"
  unavailable = "https://eq.hsc.gov.ua/images/hsc_s.png"

class Messanger:
  def __init__(self, tg_chat):
    self.size = range_dates_admissions
    self.chat = tg_chat
    self.store = {}
    self.clear_store()
  async def sync_msg(self, n, msg):
    if self.store[n] == msg: return
    self.store[n] = msg
    adapter.info(msg)
    await self.chat.answer(msg)
  def clear_store(self):
    for i in range(0, self.size):
      self.store[i] = None

def await_find_element(xpath, timeout=60, delay=0.5, container=driver):
  target_el = None
  counter = 0
  while target_el is None and counter != timeout:
    try:
      target_el = container.find_element(By.XPATH, xpath)
    except Exception:
      pass
    time.sleep(delay)
    counter += 1
  if target_el is None:
    raise Exception(f"Cannot find element by path: {xpath}")
  return target_el

def await_find_elements(xpath, timeout=60, delay=1, container=driver):
  target_els = None
  counter = 0
  while target_els is None and counter != timeout:
    try:
      target_els = container.find_elements("xpath", xpath)
    except Exception:
      pass
    time.sleep(delay)
    counter += 1
  if target_els is None:
    raise Exception(f"Cannot find element by path: {xpath}")
  return target_els

def is_el_stale(c, tries=3):
  try:
    c()
    return False 
  except Exception as err:
    if tries == 0:
      return True
    else:
      return is_el_stale(c, tries - 1)

def update_scale():
  driver.execute_script("document.body.style.zoom='70%'")

def diia_auth():
  try:
    adapter.info("Checking is auth needed...")
    driver.get("https://eq.hsc.gov.ua/site/index")
    time.sleep(1)
    if driver.current_url == "https://eq.hsc.gov.ua/site/step":
      adapter.info("No needed.")
      return 
    adapter.info("Agreeging with policy...")
    accept_checkbox = await_find_element("//input[@type='checkbox']")
    accept_checkbox.click()
    continue_btn = await_find_element("//a[@href='/openid/auth/govid']")
    continue_btn.click()
    adapter.info("Passing diia auth...")
    file_key_url_el = await_find_element(
      "//a[@class='a2' and @href='/euid-auth-js']"
    )
    file_key_url_el.click()
    time.sleep(5)
    adapter.info("Awaiting select dps...")
    select_dps_el = await_find_element(
      "//select[@class='custom-select form-control' and @id='CAsServersSelect']"
    )
    drop_el = Select(select_dps_el)
    adapter.info("Selecting dps...")
    drop_el.select_by_visible_text('КНЕДП АЦСК АТ КБ "ПРИВАТБАНК"')
    adapter.info("Uploading file key and password...")
    upload_file_el = await_find_element("//input[@accept='.dat,.pfx,.pk8,.zs2,.jks']")
    upload_file_el.send_keys(filekey_path)
    passwd_input_el = await_find_element(
      "//input[@id='PKeyPassword' and @type='password']"
    )
    passwd_input_el.send_keys(key)
    next_btn = await_find_element(
      "//button[@id='id-app-login-sign-form-file-key-sign-button' and @type='button']"
    )
    next_btn.click()
    adapter.info("Agreeing with auth...")
    update_scale()
    try:
      agree_check_el = await_find_element(
        "//input[@id='cbUserDataAgreement' and @name='cbUserDataAgreement']",
        2
      )
      adapter.info("found agree_check element")
      agree_check_el.click()
    except Exception:
      adapter.info("Agree check not found, skipping")
      pass
    adapter.info("Searching for next button...")
    next_btn = await_find_element(
      "//button[@id='btnAcceptUserDataAgreement' and @type='button']"
    )
    driver.execute_script("arguments[0].click();", next_btn)
    # next_btn.click()
    adapter.info("Passed diia auth.")
    time.sleep(1)
    driver.get("https://eq.hsc.gov.ua/site/index")
  except Exception as err:
    if driver.current_url.startswith("https://id.gov.ua/"):
      adapter.exception(
        f"Fatal error while authorizing via Diia: {repr(err)}",
      )
      exit(1)
    else:
      adapter.warning(
        f"Diia authorization error: {repr(err)}", 
      )

def check_registration_ticket():
  adapter.info("Cheking for 'Реєстраційні дії з транспортними засобами'...")
  main_btn_el = await_find_element(
    "//a[@href='/site/step_dp']"
  )
  main_btn_el.click()
  try:
    adapter.info("Closing popup...")
    close_popup_btn_el = await_find_element(
      "//div[@class='modal-dialog modal-lg']//button[@class='close' and @aria-label='Close']",
      5
    )
    close_popup_btn_el.click()
  except Exception:
    pass

def reregistration_cars():
  adapter.info("Checking for 'Перереєстрація транспортного засобу'...")
  registration_btn_el = await_find_element(
    "//button[@type='button' and contains(text(), 'Перереєстрація транспортного засобу')]"
  )
  registration_btn_el.click()
  no_btn_el = await_find_element(
    "//a[@href='/site/step1' and contains(text(), 'Ні')]"
  )
  driver.execute_script("arguments[0].click();", no_btn_el)
  tickets_btns = await_find_elements(
    "//a[@href='/site/step2']"
  )
  tickets_btns[0].click()

def get_target_content(point_element, z_index):
  global target_address, target_z_index
  driver.execute_script("arguments[0].click();", point_element)
  time.sleep(0.5)
  popup = await_find_element(
    "//div[@class='leaflet-popup-content']", 
    5,
  )
  def close_popup(popup):
    try:
      close_popup = await_find_element(
        "//a[@class='leaflet-popup-close-button']",
        5,
        container=popup
      )
      driver.execute_script("arguments[0].click();", close_popup)
    except Exception as err:
      logging.error(f"Close popup error: {repr(err)}")
  if is_el_stale(lambda: popup.get_attribute("innerText")):
    return None
  else:
    popup_content = driver.execute_script(
      "return arguments[0].innerText",
      popup
    )
  if target_address in popup_content:
    target_z_index = z_index
    if (
      point_element.get_attribute("src") == TicketsIcons.available_offline or
      point_element.get_attribute("src") == TicketsIcons.available
    ):
      close_popup(popup)
      return {
        "available": True,
        "content": popup_content
      }
    else: 
      close_popup(popup)
      return {
        "available": False,
        "content": popup_content
      }
  else:
    close_popup(popup) 
    return None

def find_target_point(points, target_z_index_changed=False):
  global target_z_index
  for i, element in enumerate(points):
    current_z_index = driver.execute_script(
      "return window.getComputedStyle(arguments[0]).getPropertyValue('z-index');", 
      element
    )
    if target_z_index_changed:
      data = get_target_content(element, current_z_index)
      if data is None: continue
      return data
    else:
      if current_z_index == target_z_index:
        data = get_target_content(element, current_z_index)
        if data is None: return find_target_point(points, True)
        return data
      else: continue

def prepare_map():
  while 1:
    try:
      zoom_out_btn = await_find_element(
        "//a[@class='leaflet-control-zoom-out']",
        timeout=3
      )
      driver.execute_script("arguments[0].click();", zoom_out_btn)
    except Exception:
      break

async def track_tickets_on_map(chat):
  adapter.info("Tracking tickets on map...")
  msg = Messanger(chat)
  while True:
    driver.refresh()
    update_scale()
    prepare_map()
    current_slide = 0
    next_btn = await_find_element(
      "//div[@id='prev' and @onclick='next()']"
    )
    while current_slide != range_dates_admissions:
      time.sleep(1)
      try:
        date = await_find_element(
          "//div[@class='services_item-lead']"
        ).text
        try:
          div_element = await_find_element(
            "//div[@class='leaflet-pane leaflet-marker-pane']",
            2
          )
        except Exception:
          continue
        img_elements = div_element.find_elements(By.TAG_NAME, "img")
        target_point = find_target_point(img_elements)
        if target_point is None:
          await msg.sync_msg(
            f"❌ Талонів на {date} немає.\n\nДодаткова інформація: Відсутня."
          )
        else:
          popup_content = target_point["content"]
          if target_point["available"]:
            # await bot.send_message(chat_id, "Увага! З'явилися нові талони.")
            await msg.sync_msg(
              current_slide,
              f"✅ Увага! Станом на {date}, появились нові талони у терміналі.\n\n" +\
                f"Додаткова інформація:\n{popup_content}\n" +\
                  f"Посилання на карту: {driver.current_url}" 
            )
          else:
            await msg.sync_msg(
              current_slide,
              f"❌ Станом на {date}, нових талонів у терміналі немає.\n\n" +\
                f"Додаткова інформація:\n{popup_content}"
            )
      except Exception as err:
        logging.exception(f"CheckTicketsError: {repr(err)}")
      current_slide += 1
      driver.execute_script("arguments[0].click();", next_btn)
    # await asyncio.sleep(60)

router = Router()

@router.message(Command("start"))
async def start_handler(msg: Message):
  try:
    await msg.answer(
      "Привіт. Повідомлятиму навяність нових талонів " +\
        f"перереєстрації ТЗ у ТСЦ МВС {target_address}.\n\n" +\
          "Починаю роботу..."
    )
    await track_tickets_on_map(msg)
  except Exception as err:
    adapter.exception(err)
    await msg.answer(
      f"Сталася помилка: {repr(err)}\n\n" +\
        "Зв'яжіться з розробником."
    )

@router.message()
async def message_handler(msg: Message):
    await msg.answer(f"Your id: {msg.from_user.id}")

async def main():
  global bot
  bot = Bot(token=TOKEN_API)
  dp = Dispatcher()
  dp.include_router(router)
  await bot.delete_webhook(drop_pending_updates=True)
  diia_auth()
  check_registration_ticket()
  reregistration_cars()
  adapter.info("Bot spawned.")
  await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == '__main__':
  asyncio.run(main())

vehicle_status = {
    "ac": {"status": "关闭", "temperature": 24, "mode": "制冷"},
    "music": {"status": "暂停", "volume": 40, "current_song": ""},
    "navigation": {"status": "关闭", "destination": ""},
    "camera": {"status": "关闭"},
    "media": {"status": "暂停", "volume": 70},
    "lights": {"status": "关闭"},
    "windows": {"status": "关闭"}
}

def normalize_chinese_text(text):
    """
    标准化中文文本，将繁体转换为简体，统一异体字
    特别针对车载系统的音乐、导航、空调功能
    """
    # 繁体到简体的映射 - 特别加强车载功能相关词汇
    traditional_to_simplified = {
        # === 基础操作词汇 ===
        '開': '开', '關': '关', '打開': '打开', '關閉': '关闭', '開啟': '开启',
        '啟動': '启动', '停止': '停止', '暫停': '暂停', '調節': '调节', '調整': '调整',
        '設置': '设置', '控制': '控制', '執行': '执行', '運行': '运行', '操作': '操作',
        
        # === 音乐/媒体相关 ===
        '音樂': '音乐', '樂': '乐', '歌曲': '歌曲', '播放': '播放', '暫停': '暂停',
        '音量': '音量', '聲音': '声音', '響度': '响度', '媒體': '媒体', '音響': '音响',
        '聲': '声', '響': '响', '頻': '频', '率': '率', '調': '调', '節': '节',
        '大聲': '大声', '小聲': '小声', '靜音': '静音', '音效': '音效', '效果': '效果',
        
        # === 导航相关 ===
        '導航': '导航', '導': '导', '航': '航', '路線': '路线', '線': '线',
        '到航': '导航',
        '到行': '导航',
        '地圖': '地图', '圖': '图', '前往': '前往', '到達': '到达', '達': '达',
        '位置': '位置', '地點': '地点', '點': '点', '目標': '目标', '標': '标',
        '路徑': '路径', '徑': '径', '方向': '方向', '導向': '导向', '指引': '指引',
        
        # === 空调相关 ===
        '空調': '空调', '調': '调', '冷氣': '冷气', '氣': '气', '暖氣': '暖气',
        '溫度': '温度', '溫': '温', '度': '度', '製冷': '制冷', '製熱': '制热',
        '風速': '风速', '風': '风', '速': '速', '檔位': '档位', '檔': '档',
        '涼': '凉', '熱': '热', '冷': '冷', '暖': '暖', '舒適': '舒适', '適': '适',
        
        
        
        # === 系统相关 ===
        '系統': '系统', '統': '统', '設備': '设备', '備': '备', '裝置': '装置',
        '裝': '装', '置': '置', '設定': '设定', '定': '定', '配置': '配置',
        '電': '电', '腦': '脑', '網': '网', '絡': '络', '連': '连', '接': '接',
        
        
        # === 时间/位置介词 ===
        '於': '于', '為': '为', '與': '与', '從': '从', '來': '来', '還': '还',
        '這': '这', '那': '那', '個': '个', '們': '们', '時': '时', '間': '间',
        
        # === 常用动词 ===
        '應': '应', '該': '该', '會': '会', '將': '将', '請': '请', '讓': '让',
        '給': '给', '對': '对', '說': '说', '話': '话', '聽': '听', '見': '见',
        '看': '看', '選': '选', '擇': '择', '選擇': '选择', '確認': '确认',
        '確': '确', '認': '认', '取消': '取消', '返回': '返回', '退出': '退出',
        
        # === 数量/程度 ===
        '個': '个', '種': '种', '類': '类', '樣': '样', '種類': '种类',
        '數量': '数量', '數': '数', '量': '量', '大小': '大小', '高低': '高低',
        '強弱': '强弱', '強': '强', '弱': '弱', '多少': '多少', '幾': '几',
        
        # === 特殊词组 ===
        '開始': '开始', '結束': '结束', '結': '结', '束': '束', '完成': '完成',
        '成功': '成功', '失敗': '失败', '敗': '败', '錯誤': '错误', '錯': '错',
        '誤': '误', '正確': '正确', '好的': '好的', '可以': '可以', '不行': '不行'
    }
    
    # 先进行词组替换（长词优先）
    result = text
    word_mappings = {
        '關閉音樂': '关闭音乐', '打開空調': '打开空调', '開啟導航': '开启导航',
        '暫停音樂': '暂停音乐', '調節溫度': '调节温度', '調整音量': '调整音量',
        '設置導航': '设置导航', '啟動系統': '启动系统', '關閉系統': '关闭系统',
        '播放音樂': '播放音乐', '停止播放': '停止播放', '開始導航': '开始导航',
        '結束導航': '结束导航', '調高音量': '调高音量', '調低音量': '调低音量',
        '調高溫度': '调高温度', '調低溫度': '调低温度', '打開車燈': '打开车灯',
        '關閉車燈': '关闭车灯', '開啟攝像頭': '开启摄像头', '關閉攝像頭': '关闭摄像头'
    }
    
    # 先替换词组
    for traditional_phrase, simplified_phrase in word_mappings.items():
        result = result.replace(traditional_phrase, simplified_phrase)
    
    # 再进行单字符替换
    final_result = ''
    for char in result:
        final_result += traditional_to_simplified.get(char, char)
    
    return final_result

def parse_voice_command(text):
    """解析语音指令并返回操作结果（支持繁简体中文）"""
    global vehicle_status
    
    # 先标准化文本（繁体转简体）
    text = normalize_chinese_text(text).lower().strip()
    
    result = {
        "success": False,
        "message": "",
        "action": "",
        "status_changes": {},
        "ui_updates": {}
    }
    
    try:
        # 空调控制 - 支持繁简体
        if any(keyword in text for keyword in ["空调", "冷气", "暖气", "空調", "冷氣", "暖氣", "制冷", "空條"]):
            if any(keyword in text for keyword in ["打开", "开启", "开", "打開", "開啟", "開", "启动", "啟動"]):
                vehicle_status["ac"]["status"] = "开启"
                result.update({
                    "success": True,
                    "message": "空调已开启",
                    "action": "ac_on",
                    "status_changes": {"ac": vehicle_status["ac"]},
                    "ui_updates": {"ac_indicator": "on", "highlight_card": "ac"}
                })
            elif any(keyword in text for keyword in ["关闭", "关", "停止", "關閉", "關", "停止", "关掉", "關掉"]):
                vehicle_status["ac"]["status"] = "关闭"
                result.update({
                    "success": True,
                    "message": "空调已关闭",
                    "action": "ac_off",
                    "status_changes": {"ac": vehicle_status["ac"]},
                    "ui_updates": {"ac_indicator": "off", "highlight_card": "ac"}
                })
            elif any(keyword in text for keyword in ["温度", "度", "溫度", "調温", "调温", "调节", "調節", "条结"]):
                # 提取温度数字
                import re
                temp_match = re.search(r'(\d+)', text)
                if temp_match:
                    temp = int(temp_match.group(1))
                    if 16 <= temp <= 30:
                        vehicle_status["ac"]["temperature"] = temp
                        result.update({
                            "success": True,
                            "message": f"空调温度已调至{temp}度",
                            "action": "ac_temp",
                            "status_changes": {"ac": vehicle_status["ac"]},
                            "ui_updates": {"ac_temp": temp, "highlight_card": "ac"}
                        })
        
        # 音乐控制 - 支持繁简体
        elif any(keyword in text for keyword in ["音乐", "歌曲", "播放", "音樂", "歌曲", "播放", "音响", "音響", "媒体", "媒體"]):
            if any(keyword in text for keyword in ["播放", "开始", "放", "播放", "開始", "放", "启动", "啟動", "打开", "打開"]):
                vehicle_status["music"]["status"] = "播放"
                result.update({
                    "success": True,
                    "message": "音乐播放已开始",
                    "action": "music_play",
                    "status_changes": {"music": vehicle_status["music"]},
                    "ui_updates": {"music_indicator": "on", "highlight_card": "music"}
                })
            elif any(keyword in text for keyword in ["暂停", "停止", "停", "暫停", "停止", "停", "关闭", "關閉","赞亭"]):
                vehicle_status["music"]["status"] = "暂停"
                result.update({
                    "success": True,
                    "message": "音乐已暂停",
                    "action": "music_pause",
                    "status_changes": {"music": vehicle_status["music"]},
                    "ui_updates": {"music_indicator": "off", "highlight_card": "music"}
                })
            elif any(keyword in text for keyword in ["音量", "音量", "声音", "聲音", "大小", "大小"]):
                import re
                volume_match = re.search(r'(\d+)', text)
                if volume_match:
                    volume = int(volume_match.group(1))
                    if 0 <= volume <= 100:
                        vehicle_status["music"]["volume"] = volume
                        result.update({
                            "success": True,
                            "message": f"音量已调至{volume}%",
                            "action": "music_volume",
                            "status_changes": {"music": vehicle_status["music"]},
                            "ui_updates": {"music_volume": volume, "highlight_card": "music"}
                        })
        
        # 导航控制 - 支持繁简体
        elif any(keyword in text for keyword in ["导航", "路线", "地图", "導航", "路線", "地圖", "gps", "GPS","到航","到行"]):
            if any(keyword in text for keyword in ["打开", "开启", "开始", "打開", "開啟", "開始", "启动", "啟動"]):
                vehicle_status["navigation"]["status"] = "开启"
                result.update({
                    "success": True,
                    "message": "导航已开启",
                    "action": "nav_on",
                    "status_changes": {"navigation": vehicle_status["navigation"]},
                    "ui_updates": {"nav_indicator": "on", "highlight_card": "navigation"}
                })
            elif any(keyword in text for keyword in ["关闭", "关", "停止", "關閉", "關", "停止", "结束", "結束"]):
                vehicle_status["navigation"]["status"] = "关闭"
                result.update({
                    "success": True,
                    "message": "导航已关闭",
                    "action": "nav_off",
                    "status_changes": {"navigation": vehicle_status["navigation"]},
                    "ui_updates": {"nav_indicator": "off", "highlight_card": "navigation"}
                })
            elif any(keyword in text for keyword in ["到", "去", "到", "去", "前往", "前往"]):
                # 提取目的地
                destination = text.split("到")[-1].split("去")[-1].strip()
                if destination:
                    vehicle_status["navigation"]["destination"] = destination
                    vehicle_status["navigation"]["status"] = "开启"
                    result.update({
                        "success": True,
                        "message": f"正在导航至{destination}",
                        "action": "nav_destination",
                        "status_changes": {"navigation": vehicle_status["navigation"]},
                        "ui_updates": {"nav_indicator": "on", "nav_destination": destination, "highlight_card": "navigation"}
                    })
        
        # 未识别的指令
        else:
            result.update({
                "success": False,
                "message": f"抱歉，我无法理解指令：{text}。请尝试说'打开空调'、'播放音乐'等指令",
                "action": "unknown"
            })
            
    except Exception as e:
        result.update({
            "success": False,
            "message": f"指令处理出错：{str(e)}",
            "action": "error"
        })
    
    return result
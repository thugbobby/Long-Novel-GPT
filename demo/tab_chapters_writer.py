import json
import gradio as gr

from demo.gr_utils import messages2chatbot, block_diff_text, create_model_radio, create_selected_text, enable_change_output, generate_cost_info


def tab_chapters_writer(config):
    lngpt = config['lngpt']
    FLAG = {
        'running': 0,
        'cancel': 0,
    }

    def get_writer():
        nonlocal lngpt
        lngpt = config['lngpt']
        if not lngpt:
            return None
        return lngpt.get_writer('chapters')

    with gr.Tab("生成章节") as tab:
        with gr.Row():
            def get_inputs_text():
                return get_writer().get_input_context()
            
            inputs = gr.Textbox(label="大纲", lines=10, interactive=False)

            def get_output_text():
                return get_writer().get_output()

            output = gr.Textbox(label="章节剧情", lines=10, interactive=True)

        def create_option(value):
            available_options = ["讨论", "新建章节剧情", ]
            if get_writer().get_chapter_names():
                available_options.append("重写章节剧情")

            return gr.Radio(
                choices=available_options,
                label="选择你要进行的操作",
                value=value,
            )
        model = create_model_radio()        
        option = gr.Radio()

        def create_sub_option(option_value):
            if option_value == '新建章节剧情':
                return gr.Radio(["全部章节"], label="选择章节", value="")
            elif option_value == '重写章节剧情':
                return gr.Radio(get_writer().get_chapter_names(), label="选择章节", value='')
            elif option_value == '讨论':
                return gr.Radio(["全部章节"] + get_writer().get_chapter_names(), label="选择章节", value='')

        sub_option = gr.Radio()

        selected_output_text = create_selected_text(output)
        enable_change_output(get_writer, output)

        def create_human_feedback(option_value):
            if option_value == '新建章节剧情':
                return gr.Textbox(value="", label="你的意见：", lines=2, placeholder="让AI知道你的意见，这在优化阶段会更有用。")
            elif option_value == '重写章节剧情':
                return gr.Textbox(value="请从情节推动不合理，剧情不符合逻辑，条理不清晰等方面进行反思。", label="你的意见：", lines=2)
            elif option_value == '讨论':
                return gr.Textbox(value="不要急于得出结论，让我们先一步一步的思考", label="你的意见：", lines=2)

        human_feedback = gr.Textbox()

        def on_select_option(evt: gr.SelectData):
            return create_sub_option(evt.value), create_human_feedback(evt.value)

        option.select(on_select_option, None, [sub_option, human_feedback])

        cost_info = gr.Markdown('当前操作预计消耗：0$')
        start_button = gr.Button("开始")
        rollback_button = gr.Button("撤销（不可撤销正在进行的操作）")

        chatbot = gr.Chatbot()
        def check_running(func):
            def wrapper(*args, **kwargs):
                # if FLAG['running'] == 1:
                #     gr.Info("当前有操作正在进行，请稍后再试！")
                #     return

                FLAG['running'] = 1
                try:
                    for ret in func(*args, **kwargs):
                        if FLAG['cancel']:
                            FLAG['cancel'] = 0
                            break
                        yield ret
                except Exception as e:
                    raise gr.Error(str(e))
                finally:
                    FLAG['running'] = 0
            return wrapper
        
        @check_running
        def on_submit(option, sub_option, human_feedback, selected_output_text):
            selected_output_text = selected_output_text.strip()
            if sub_option == '全部章节':
                sub_option = None
            else:
                sub_option = sub_option
                    
            match option:
                case '讨论':
                    for messages in get_writer().discuss(human_feedback):
                        yield messages2chatbot(messages), generate_cost_info(messages)
                case "新建章节剧情":
                    for messages in get_writer().init_chapters(human_feedback=human_feedback, selected_text=selected_output_text):
                        yield messages2chatbot(messages), generate_cost_info(messages)
                case "重写章节剧情":
                    for i, messages in enumerate(get_writer().rewrite_chatpers(chapter_name=sub_option, human_feedback=human_feedback, selected_text=selected_output_text)):
                        yield messages2chatbot(messages), generate_cost_info(messages)
                        if i == 0 and not selected_output_text:
                            raise gr.Error('请先在正文栏中选定要重写的部分！')
        
        def save():
            lngpt.save('chapters')
    
        def rollback(i):
            return lngpt.rollback(i, 'chapters')  
        
        def on_roll_back():
            # if FLAG['running'] == 1:
            #     FLAG['cancel'] = 1
            #     FLAG['running'] = 0
            #     gr.Info("已暂停当前操作！")
            #     return

            if rollback(1):
                gr.Info("撤销成功！")
            else:
                gr.Info("已经是最早的版本了")
        
        @gr.on(triggers=[model.select, sub_option.select, human_feedback.change], inputs=[model, option, sub_option, human_feedback, selected_output_text], outputs=[chatbot, cost_info])
        def on_cost_change(model, option, sub_option, human_feedback, selected_output_text):
            config['lngpt'].get_writer('novel').set_cur_chapter_name(sub_option if sub_option != "全部章节" else None)
            if model: get_writer().set_model(model)
            if option and sub_option:
                messages, cost_info = next(on_submit(option, sub_option, human_feedback, selected_output_text))
                return messages, cost_info
            else:
                return None, None

        start_button.click(on_submit, [option, sub_option, human_feedback, selected_output_text], [chatbot, cost_info]).success(
            save).then(
            lambda option: (get_output_text(), create_option(option), create_sub_option(option)), option, [output, option, sub_option]
        )

        rollback_button.click(on_roll_back, None, None).success(
            lambda option: (get_output_text(), create_option(''), create_sub_option(option), []), option, [output, option, sub_option, chatbot]
        )
    
    def on_select_tab():
        if get_writer():
            return get_inputs_text(), get_output_text(), create_option(''), create_sub_option(''), []
        else:
            gr.Info("请先选择小说名！")
            return gr.Textbox(''), gr.Textbox(''), gr.Radio([]), gr.Radio([]), []
    
    tab.select(on_select_tab, None, [inputs, output, option, sub_option, chatbot])
    

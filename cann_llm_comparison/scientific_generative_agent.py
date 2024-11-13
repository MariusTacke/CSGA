﻿import re
import copy

import loader
import exporter
import evaluator
import prompt_writer
import chatting_llm_azure


class ScientificGenerativeAgent():

    def __init__(self, config):
        self._config        = config
        self._llm           = chatting_llm_azure.ChattingLLMAzure()
        self._prompt_writer = prompt_writer.PromptWriter(config)
        self._loader        = loader.Loader(             config)
        self._evaluator     = evaluator.Evaluator(       config)
        self._exporter      = exporter.Exporter(         config)

        self._iterations    = 5
        self._top_k         = 3
        self._top_k_models  = []


    def set_up(self):
        self._llm.set_up()
        self._exporter.set_up()
        self._loader.load()


    def run(self):
        system_prompt = self._prompt_writer.write_system_prompt()
        user_prompt   = self._prompt_writer.write_user_prompt(loader=self._loader)
        fit_code      = self._prompt_writer.write_fit_code()

        for iteration in range(self._iterations):
            def _recursive_generate_and_evaluate_model(attempts=0, max_attempts=3):
                try:
                    return self._generate_and_evaluate_model(
                        system_prompt, user_prompt, fit_code
                    )
                except Exception as e:
                    print(f"Repeating iteration {iteration} due to error: {e}")
                    if attempts < max_attempts:
                        return _recursive_generate_and_evaluate_model(attempts+1, max_attempts)
                    else:
                        print("Max attempts reached. Operation failed.")
                        return None
            model, model_code = _recursive_generate_and_evaluate_model()
            loss              = self._evaluator.evaluate(iteration, self._loader, model)

            self._save_model(model, model_code, loss)

        model, model_code, _ = self._load_best_model()
        self._exporter.export(self._loader, model, model_code)


    def _generate_and_evaluate_model(self, system_prompt, user_prompt, fit_code):
        # Outer-Level Optimization: Ask LLM for forward equation based on previous iterations
        prev = ""
        for idx, (_, top_k_model_code, top_k_model_loss) in enumerate(self._top_k_models):
            prev += f"### Previous iteration #{idx}:\n\n{                   top_k_model_code}\n\n"
            prev += f"### Feedback on previous iteration #{idx}:\n\nLoss = {top_k_model_loss}\n\n"
        user_prompt = prev + user_prompt
        messages = [
            {"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}
        ]
        response = self._llm.chat(messages)

        # Execution of proposed code
        model_code = re.findall(r"```python(.*?)```", response, re.DOTALL)[0].strip()
        namespace = {}
        exec(model_code + fit_code, namespace)
        model = namespace["Physics"]()

        # Inner-Level Optimization: Optimize parameters
        model.fit(x = self._loader.get_train_data_x(), y = self._loader.get_train_data_y())

        return model, model_code


    def _save_model(self, model, model_code, loss):
        self._top_k_models.append([copy.deepcopy(model), model_code, loss])
        # Sort models by loss
        self._top_k_models.sort(key=lambda x: x[2])
        # Keep only the top k models
        self._top_k_models = self._top_k_models[:self._top_k]


    def _load_best_model(self):
        return self._top_k_models[0]

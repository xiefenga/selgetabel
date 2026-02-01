1. excel 文件读取之后预处理，比如：去除无效列
2. execute 阶段存在 errors，还是 done 的状态
3. 出现系统级 error 时，需不需要修复最后一个 step 的 status
4. validate 阶段，添加其他的校验（字段），或者执行阶段出错也按情况重新 generate
5. 操作符的行为，和 excel 本身保持一致：https://chatgpt.com/c/697f58a9-7408-8321-8887-4e3575d231f7

function Code(code)
  if FORMAT:match("latex") and #code.text > 32 and code.text:match("[/._%-]") then
    return pandoc.RawInline("latex", "\\nolinkurl{" .. code.text .. "}")
  end
  return code
end

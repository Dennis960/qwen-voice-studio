from app.models.generation import Style
PROMPTS={'neutral':'a natural, balanced and composed delivery','happy':'genuine happiness and a bright uplift','cheerful':'a buoyant, friendly cheerfulness','excited':'vivid excitement and animated emphasis','calm':'a calm, steady and unhurried presence','warm':'warmth, kindness and approachable reassurance','sad':'restrained sadness with soft, reflective phrasing','angry':'anger and determination with firm, controlled emphasis','frustrated':'contained frustration and impatient emphasis','fearful':'audible apprehension and cautious tension','nervous':'gentle nervousness with tentative pacing','surprised':'clear surprise with responsive emphasis','serious':'a serious, focused and deliberate tone','dramatic':'cinematic drama with intentional pauses and dynamic emphasis','confident':'calm confidence, clarity and assured emphasis','gentle':'a gentle, tender and soothing quality','whispering':'a close, soft whisper while keeping words intelligible'}
def build_instruction(description:str, style:Style|None)->str:
    style=style or Style(); level='subtle' if style.intensity<=.25 else 'moderate' if style.intensity<=.6 else 'strong' if style.intensity<=.85 else 'very strong'
    parts=[f'Speak as {description.strip().rstrip(".")}',f'Use {PROMPTS[style.emotion]} at {level} emotional intensity']
    if style.pace: parts.append(f'Keep the pace {style.pace.replace("_","-")}')
    if style.energy: parts.append(f'Maintain {style.energy} energy')
    if style.pitch: parts.append(f'Use a {style.pitch} pitch range')
    return '. '.join(parts)+'.'

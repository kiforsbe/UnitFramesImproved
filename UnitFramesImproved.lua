-- Create the addon main instance (Ace-3.0)
UnitFramesImproved = LibStub("AceAddon-3.0"):NewAddon("UnitFramesImproved", "AceConsole-3.0", "AceEvent-3.0")
UnitFramesImproved:SetDefaultModuleLibraries("AceConsole-3.0", "AceEvent-3.0")
UnitFramesImproved:SetDefaultModuleState(false)

-- Initialization of the addon, compatible with Ace-3.0
function UnitFramesImproved:OnInitialize()
  DebugPrint("OK", "INFO", 2, "Initializing...")

  -- Register event handlers
  self:RegisterEvent('PLAYER_TARGET_CHANGED', 'PLAYER_TARGET_CHANGED')
  self:RegisterEvent('PLAYER_FOCUS_CHANGED', 'PLAYER_FOCUS_CHANGED')
  self:RegisterEvent('UNIT_TARGET', "UNIT_TARGET")

  -- Register chat slash-commands
  self:RegisterChatCommand("ufi", "SlashCommand_Main")
  self:RegisterChatCommand("unitframesimproved", "SlashCommand_Main")

  DebugPrint("OK", "INFO", 2, "Initialized.")
end

function UnitFramesImproved:LoadConfig()
  DebugPrint("OK", "INFO", 2, "Loading config...")

  -- Set up default stylings
  UnitFramesImproved:Style_PlayerFrame()
  UnitFramesImproved:Style_TargetFrame(TargetFrame)
  UnitFramesImproved:Style_TargetFrame(FocusFrame)
  UnitFramesImproved:Style_ToTFrame(TargetFrameToT)
  UnitFramesImproved:Style_ToTFrame(FocusFrameToT)

  DebugPrint("OK", "INFO", 2, "Config loaded.")
end

-- Slash-command Handlers
function UnitFramesImproved:SlashCommand_Main()
  -- For now just output some info that settings for scale have been removed from previous major versions
  dout("Welcome to UnitFramesImproved. Settings have been removed as this is part of standard UI.")
end

-- Event Handlers
function UnitFramesImproved:PLAYER_TARGET_CHANGED()
  UnitFramesImproved:Style_TargetFrame(TargetFrame)
  UnitFramesImproved:UpdateStatusBarColor(TargetFrame)
end

function UnitFramesImproved:PLAYER_FOCUS_CHANGED()
  UnitFramesImproved:Style_TargetFrame(FocusFrame)
  UnitFramesImproved:UpdateStatusBarColor(FocusFrame)
end

function UnitFramesImproved:UNIT_TARGET(self, unitTarget)
  if unitTarget == "target" then
    UnitFramesImproved:Style_ToTFrame(TargetFrameToT)
    UnitFramesImproved:UpdateStatusBarColor(TargetFrameToT)
  end
  if unitTarget == "focus" then
    UnitFramesImproved:Style_ToTFrame(FocusFrameToT)
    UnitFramesImproved:UpdateStatusBarColor(FocusFrameToT)
  end
end

-- Common Functions
function UnitFramesImproved_UpdateTextStringWithValues(statusFrame, textString, value, valueMin, valueMax)
  if (false and statusFrame.LeftText and statusFrame.RightText) then
    --if not InCombatLockdown() then
      if (textString) then
        statusFrame.LeftText:SetText("")
        statusFrame.RightText:SetText("")
        statusFrame.LeftText:Hide()
        statusFrame.RightText:Hide()

        textString:Show()
      end
    --end
  end

	if ( ( tonumber(valueMax) ~= valueMax or valueMax > 0 ) and not ( statusFrame.pauseUpdates ) ) then
		local valueDisplay = UnitFramesImproved:AbbreviateLargeNumbers(value);
		local valueMaxDisplay = UnitFramesImproved:AbbreviateLargeNumbers(valueMax);

		local textDisplay = GetCVar("statusTextDisplay");
		if ( value and valueMax > 0 and ( (textDisplay ~= "NUMERIC" and textDisplay ~= "NONE") or statusFrame.showPercentage ) and not statusFrame.showNumeric) then
			if ( value == 0 and statusFrame.zeroText ) then
				textString:SetText(statusFrame.zeroText);
				statusFrame.isZero = 1;
				textString:Show();
			elseif ( textDisplay == "BOTH" and not statusFrame.showPercentage) then
				if( statusFrame.LeftText and statusFrame.RightText ) then
					if(not statusFrame.powerToken or statusFrame.powerToken == "MANA") then
						statusFrame.LeftText:SetText(math.ceil((value / valueMax) * 100) .. "%");
						statusFrame.LeftText:Show();
					end
					statusFrame.RightText:SetText(valueDisplay);
					statusFrame.RightText:Show();
					textString:Hide();
				else
					valueDisplay = "(" .. math.ceil((value / valueMax) * 100) .. "%) " .. valueDisplay .. " / " .. valueMaxDisplay;
				end
				textString:SetText(valueDisplay);
			else
				valueDisplay = math.ceil((value / valueMax) * 100) .. "%";
				if ( statusFrame.prefix and (statusFrame.alwaysPrefix or not (statusFrame.cvar and GetCVar(statusFrame.cvar) == "1" and statusFrame.textLockable) ) ) then
					textString:SetText(statusFrame.prefix .. " " .. valueDisplay);
				else
					textString:SetText(valueDisplay);
				end
			end
		elseif ( value == 0 and statusFrame.zeroText ) then
			textString:SetText(statusFrame.zeroText);
			statusFrame.isZero = 1;
			textString:Show();
			return;
		else
			statusFrame.isZero = nil;
			if ( statusFrame.prefix and (statusFrame.alwaysPrefix or not (statusFrame.cvar and GetCVar(statusFrame.cvar) == "1" and statusFrame.textLockable) ) ) then
				textString:SetText(statusFrame.prefix.." "..valueDisplay.." / "..valueMaxDisplay);
			else
				textString:SetText(valueDisplay.." / "..valueMaxDisplay);
			end
		end
	else
		textString:Hide();
		textString:SetText("");
		if ( not statusFrame.alwaysShow ) then
			statusFrame:Hide();
		else
			statusFrame:SetValue(0);
		end
	end
end

function UnitFramesImproved:UpdateStatusBarColor(frame)
  -- Set back color of health bar
  if (not UnitPlayerControlled(frame.unit) and UnitIsTapDenied(frame.unit)) then
    -- Gray if npc is tapped by other player
    frame.healthbar:SetStatusBarColor(0.5, 0.5, 0.5)
  else
    -- Standard by class etc if not
    local r, g, b = UnitFramesImproved:UnitColor(frame.healthbar.unit)
    frame.healthbar:SetStatusBarColor(r, g, b)
  end
end

-- Utility functions
function UnitFramesImproved:UnitColor(unit)
  local r, g, b
  if ((not UnitIsPlayer(unit)) and ((not UnitIsConnected(unit)) or (UnitIsDeadOrGhost(unit)))) then
    --Color it gray
    r, g, b = 0.5, 0.5, 0.5
  elseif (UnitIsPlayer(unit)) then
    --Try to color it by class.
    local localizedClass, englishClass = UnitClass(unit)
    local classColor = (CUSTOM_CLASS_COLORS or RAID_CLASS_COLORS)[englishClass]
    if (classColor) then
      r, g, b = classColor.r, classColor.g, classColor.b
    else
      if (UnitIsFriend("player", unit)) then
        r, g, b = 0.0, 1.0, 0.0
      else
        r, g, b = 1.0, 0.0, 0.0
      end
    end
  else
    r, g, b = UnitSelectionColor(unit)
  end

  return r, g, b
end

function UnitFramesImproved:AbbreviateLargeNumbers(value)
  local strLen = strlen(value)
  local retString = value

  if (strLen >= 10) then
    retString = string.sub(value, 1, -10) .. "." .. string.sub(value, -9, -8) .. "G"
  elseif (strLen >= 7) then
    retString = string.sub(value, 1, -7) .. "." .. string.sub(value, -6, -5) .. "M"
  elseif (strLen >= 4) then
    retString = string.sub(value, 1, -4) .. "." .. string.sub(value, -3, -3) .. "k"
  end

  return retString
end

function UnitFramesImproved:CreateStatusBarText(name, parentName, parent, point, x, y)
	local fontString = parent:CreateFontString(parentName..name, nil, "TextStatusBarText")
	fontString:SetPoint(point, parent, point, x, y)
	
	return fontString
end

function UnitFramesImproved:SetFontSize(fontString, size)
  if(fontString ~= nil and size > 0) then
    -- Retrieve the current font settings
    local font, _, flags = fontString:GetFont()

    -- Set the font again with the new size
    fontString:SetFont(font, size, flags)
  end
end

-- Events
UnitFramesImproved:RegisterEvent("PLAYER_ENTERING_WORLD", "LoadConfig")

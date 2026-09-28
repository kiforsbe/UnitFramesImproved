-- The addon's shared table. Kept global (rather than only the private `...` namespace table)
-- because the per-client styler files and UnitFramesImproved_Options.lua all extend it, and it's
-- handy for /dump while debugging.
UnitFramesImproved = {}

-- Blizzard-native event handling: one private frame, with each event dispatched to the addon
-- method of the same name. This used to go through AceAddon/AceEvent/AceConsole, which only ever
-- wrapped exactly this and the SlashCmdList registration at the bottom of this file - see
-- ARCHITECTURE.md. A private frame (rather than Blizzard's shared EventRegistry) keeps our
-- handlers out of any state Blizzard's own code also iterates over.
local eventFrame = CreateFrame("Frame")
eventFrame:SetScript("OnEvent", function(_, event, ...)
  UnitFramesImproved[event](UnitFramesImproved, ...)
end)

function UnitFramesImproved:LoadConfig()
  -- LoadConfig re-runs on every PLAYER_ENTERING_WORLD (fires on every zone/loading screen,
  -- not just initial login) and on PLAYER_REGEN_ENABLED (combat-lockdown catch-up), so only
  -- announce the very first application - re-applications should stay silent.
  local isFirstLoad = not UnitFramesImproved.configLoadedOnce
  if (isFirstLoad) then
    DebugPrint("OK", "INFO", 2, "Loading config...")
  end

  -- Set up default stylings
  UnitFramesImproved:Style_PlayerFrame()
  UnitFramesImproved:Style_TargetFrame(TargetFrame)
  UnitFramesImproved:Style_TargetFrame(FocusFrame)
  UnitFramesImproved:Style_ToTFrame(TargetFrameToT)
  UnitFramesImproved:Style_ToTFrame(FocusFrameToT)

  if (isFirstLoad) then
    DebugPrint("OK", "INFO", 2, "Config loaded.")
    UnitFramesImproved.configLoadedOnce = true
  end
end

-- Slash-command Handlers
function UnitFramesImproved:SlashCommand_Main()
  -- OpenOptions is defined by UnitFramesImproved_Options.lua, which leaves it unset on a client
  -- without Blizzard's Settings API.
  if (self.OpenOptions) then
    self:OpenOptions()
  else
    dout("UnitFramesImproved: this client has no options panel to open.")
  end
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

function UnitFramesImproved:UNIT_TARGET(unitTarget)
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
function UnitFramesImproved.UpdateTextStringWithValues(statusFrame, textString, value, valueMin, valueMax)
  if (statusFrame.LeftText and statusFrame.RightText and textString) then
    statusFrame.LeftText:SetText("")
    statusFrame.RightText:SetText("")
    statusFrame.LeftText:Hide()
    statusFrame.RightText:Hide()

    textString:Show()
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
	end
end

function UnitFramesImproved:UpdateStatusBarColor(frame)
  -- frame/frame.healthbar can be nil - e.g. TargetFrameToT/FocusFrameToT don't exist on
  -- every client, and Style_ToTFrame doesn't guarantee .healthbar gets set on them.
  if (not frame or not frame.healthbar) then
    return
  end

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
    local classColor = RAID_CLASS_COLORS[englishClass]
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
  -- Retail (Midnight+) can hand us a secret value here (e.g. health while its actual
  -- number is being withheld). issecretvalue() only exists on Retail; on Classic this
  -- branch is simply never taken. Reading a secret's digits via strlen/string.sub
  -- errors once execution is addon-tainted, so pass it through untouched instead -
  -- Blizzard's own downstream code is built to display secrets safely, ours isn't.
  if (issecretvalue and issecretvalue(value)) then
    return value
  end

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

-- Anchors `region` at a fixed (dx,dy) offset from its OWN first-ever observed
-- anchor, cached on the region itself, rather than re-reading GetPoint() and
-- re-adding the offset on every call. Style_TargetFrame runs on every target
-- switch and Blizzard never resets TargetFrameHealthBar's anchor between switches
-- (unlike PlayerFrame, which Blizzard resets every PLAYER_ENTERING_WORLD) - reading
-- our own last result and adding the offset again would drift further with every
-- retarget. ClearAllPoints first because Blizzard's default template can anchor
-- both corners at once; GetPoint() only reports one of them.
function UnitFramesImproved:OffsetAnchor(region, dx, dy)
  if (not region.ufiBaseAnchor) then
    local point, relativeTo, relativePoint, xOfs, yOfs = region:GetPoint()
    region.ufiBaseAnchor = { point, relativeTo, relativePoint, xOfs, yOfs }
  end
  local base = region.ufiBaseAnchor
  region:ClearAllPoints()
  region:SetPoint(base[1], base[2], base[3], base[4] + dx, base[5] + dy)
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
function UnitFramesImproved:PLAYER_ENTERING_WORLD()
  self:LoadConfig()
end

-- Catch-up: LoadConfig's InCombatLockdown-guarded region creation (e.g. Style_TargetFrame's
-- CreateStatusBarText fallback) can be skipped if PLAYER_ENTERING_WORLD or a target/focus
-- change happens mid-combat. Re-running LoadConfig on leaving combat is safe to repeat -
-- OffsetAnchor caches its own baseline and region creation is guarded by a nil check - so
-- this just picks up anything that was skipped, without redoing/drifting anything that wasn't.
function UnitFramesImproved:PLAYER_REGEN_ENABLED()
  self:LoadConfig()
end

eventFrame:RegisterEvent("PLAYER_ENTERING_WORLD")
eventFrame:RegisterEvent("PLAYER_REGEN_ENABLED")
eventFrame:RegisterEvent("PLAYER_TARGET_CHANGED")
eventFrame:RegisterEvent("PLAYER_FOCUS_CHANGED")
eventFrame:RegisterEvent("UNIT_TARGET")

-- Slash commands, via Blizzard's own SlashCmdList (replaces AceConsole's RegisterChatCommand).
SLASH_UNITFRAMESIMPROVED1 = "/ufi"
SLASH_UNITFRAMESIMPROVED2 = "/unitframesimproved"
SlashCmdList["UNITFRAMESIMPROVED"] = function()
  UnitFramesImproved:SlashCommand_Main()
end
